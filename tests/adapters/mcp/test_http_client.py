"""Tests for HttpMcpClient, using httpx.MockTransport instead of a real server."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from sensai.adapters.mcp.http_client import PROTOCOL_VERSION, HttpMcpClient
from sensai.core.ports import McpToolError, McpUnavailableError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

URL = "https://mcp.test/mcp/"
SERVER_INFO = {"io.modelcontextprotocol/serverInfo": {"name": "fake", "version": "1"}}

# Maps a JSON-RPC method to the JSON-RPC message the fake server answers with,
# without `jsonrpc` and `id`, which `_server` fills in from the request.
type Replies = dict[str, dict[str, Any]]


def _server(
    replies: Replies,
    seen: list[httpx.Request] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.MockTransport:
    """Return a transport that answers each method with its canned reply."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        payload = json.loads(request.content)
        reply = {"jsonrpc": "2.0", "id": payload["id"], **replies[payload["method"]]}
        return httpx.Response(
            200, json=reply, headers={"Mcp-Session-Id": "sess-1", **(headers or {})}
        )

    return httpx.MockTransport(handler)


def _with_discover(replies: Replies) -> Replies:
    return {"server/discover": {"result": {"_meta": SERVER_INFO}}, **replies}


def _run[T](
    transport: httpx.MockTransport,
    action: Callable[[HttpMcpClient], Awaitable[T]],
) -> T:
    """Connect a client over `transport`, run `action`, then close it."""

    async def run() -> T:
        client = HttpMcpClient("fake", URL, transport=transport)
        await client.connect()
        try:
            return await action(client)
        finally:
            await client.aclose()

    return asyncio.run(run())


def _tool_result(content: list[dict[str, Any]], *, is_error: bool = False) -> Replies:
    return _with_discover(
        {"tools/call": {"result": {"content": content, "isError": is_error}}}
    )


def test_connect_sends_meta_and_reuses_the_session_id() -> None:
    """Requests carry `_meta` and the method header; the session id is echoed."""
    seen: list[httpx.Request] = []
    transport = _server(_with_discover({"tools/list": {"result": {"tools": []}}}), seen)

    _run(transport, lambda client: client.list_tools())

    discover, tools_list = seen
    assert discover.headers["Mcp-Method"] == "server/discover"
    meta = json.loads(discover.content)["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert "Mcp-Session-Id" not in discover.headers
    assert tools_list.headers["Mcp-Session-Id"] == "sess-1"


def test_connect_fails_when_discover_returns_an_error() -> None:
    """A JSON-RPC error during discovery makes the server unavailable."""
    transport = _server({"server/discover": {"error": {"message": "nope"}}})

    with pytest.raises(McpUnavailableError, match="nope"):
        _run(transport, lambda client: asyncio.sleep(0))


def test_connect_fails_on_an_unsupported_protocol_version() -> None:
    """A server answering with another protocol version is unavailable."""
    transport = _server(
        _with_discover({}), headers={"Mcp-Protocol-Version": "2025-06-18"}
    )

    with pytest.raises(McpUnavailableError, match="unsupported protocol version"):
        _run(transport, lambda client: asyncio.sleep(0))


def test_connect_accepts_the_supported_protocol_version() -> None:
    """A server echoing the client's protocol version connects."""
    transport = _server(
        _with_discover({}), headers={"Mcp-Protocol-Version": PROTOCOL_VERSION}
    )

    _run(transport, lambda client: asyncio.sleep(0))


def test_list_tools_maps_specs_and_defaults_optional_fields() -> None:
    """Read-only tools need no confirmation; unannotated ones do."""
    tools = [
        {
            "name": "get_issue",
            "description": "Get an issue",
            "inputSchema": {"type": "object", "properties": {}},
            "annotations": {"readOnlyHint": True},
        },
        {"name": "create_issue", "inputSchema": {"type": "object"}},
    ]
    transport = _server(_with_discover({"tools/list": {"result": {"tools": tools}}}))

    read_only, unannotated = _run(transport, lambda client: client.list_tools())

    assert (read_only.name, read_only.description) == ("get_issue", "Get an issue")
    assert read_only.requires_confirmation is False
    assert (unannotated.name, unannotated.description) == ("create_issue", "")
    assert unannotated.requires_confirmation is True


def test_list_tools_raises_unavailable_on_a_json_rpc_error() -> None:
    """A JSON-RPC error on `tools/list` is not a `KeyError`."""
    transport = _server(_with_discover({"tools/list": {"error": {"message": "boom"}}}))

    with pytest.raises(McpUnavailableError, match="tools/list failed: boom"):
        _run(transport, lambda client: client.list_tools())


def test_call_tool_joins_the_text_content() -> None:
    """Text blocks are joined by newlines; other content types are dropped."""
    seen: list[httpx.Request] = []
    content = [
        {"type": "text", "text": "line 1"},
        {"type": "image", "data": "...", "mimeType": "image/png"},
        {"type": "text", "text": "line 2"},
    ]
    transport = _server(_tool_result(content), seen)

    text = _run(transport, lambda client: client.call_tool("echo", {"x": 1}))

    assert text == "line 1\nline 2"
    assert seen[-1].headers["Mcp-Name"] == "echo"
    assert json.loads(seen[-1].content)["params"]["arguments"] == {"x": 1}


def test_call_tool_raises_tool_error_when_the_result_is_an_error() -> None:
    """A result flagged `isError` raises with the tool's own message."""
    transport = _server(
        _tool_result([{"type": "text", "text": "rate limited"}], is_error=True)
    )

    with pytest.raises(McpToolError, match="echo failed: rate limited"):
        _run(transport, lambda client: client.call_tool("echo", {}))


def test_call_tool_raises_tool_error_on_a_json_rpc_error() -> None:
    """A protocol error, such as an unknown tool, raises a tool error."""
    transport = _server(
        _with_discover({"tools/call": {"error": {"message": "unknown tool"}}})
    )

    with pytest.raises(McpToolError, match="unknown tool"):
        _run(transport, lambda client: client.call_tool("missing", {}))


def _respond_to_tools_list(
    respond: Callable[[int], httpx.Response],
) -> httpx.MockTransport:
    """Answer discovery normally and `tools/list` with `respond(request_id)`."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "server/discover":
            reply = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"_meta": SERVER_INFO},
            }
            return httpx.Response(200, json=reply)
        return respond(payload["id"])

    return httpx.MockTransport(handler)


def _sse(*messages: dict[str, Any]) -> httpx.Response:
    body = "".join(f"event: message\ndata: {json.dumps(m)}\n\n" for m in messages)
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def test_event_stream_skips_notifications_until_the_response() -> None:
    """In an SSE reply, only the message with the request's id is returned."""
    notification = {"jsonrpc": "2.0", "method": "notifications/progress"}

    def respond(request_id: int) -> httpx.Response:
        tool = {"name": "t", "inputSchema": {"type": "object"}}
        response = {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [tool]}}
        return _sse(notification, response)

    transport = _respond_to_tools_list(respond)

    tools = _run(transport, lambda client: client.list_tools())

    assert [tool.name for tool in tools] == ["t"]


@pytest.mark.parametrize(
    ("response", "match"),
    [
        (httpx.Response(500, text="oops"), "HTTP 500 for tools/list: oops"),
        (_sse({"jsonrpc": "2.0", "method": "ping"}), "stream ended without"),
        (httpx.Response(200, text="hi"), "unexpected content-type"),
    ],
    ids=["http-error", "stream-without-response", "bad-content-type"],
)
def test_bad_transport_replies_raise_unavailable(
    response: httpx.Response, match: str
) -> None:
    """HTTP errors and malformed replies make the server unavailable."""
    transport = _respond_to_tools_list(lambda _: response)

    with pytest.raises(McpUnavailableError, match=match):
        _run(transport, lambda client: client.list_tools())


def test_calls_before_connect_raise_unavailable() -> None:
    """Using the client before `connect` fails cleanly."""
    client = HttpMcpClient("fake", URL)

    with pytest.raises(McpUnavailableError, match="not connected"):
        asyncio.run(client.list_tools())


def test_aclose_is_safe_twice_and_before_connect() -> None:
    """Closing never fails, connected or not."""

    async def run() -> None:
        client = HttpMcpClient("fake", URL, transport=_server(_with_discover({})))
        await client.aclose()
        await client.connect()
        await client.aclose()
        await client.aclose()

    asyncio.run(run())
