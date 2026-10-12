"""MCP client over the Streamable HTTP transport."""

from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from sensai.core.models import ToolSpec
from sensai.core.ports import McpToolError, McpUnavailableError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class HttpMcpClient:
    """Connection to a remote MCP server over Streamable HTTP.

    Implements the `McpClient` port. Targets the stateless 2026-07-28 protocol:
    each JSON-RPC request carries its own `_meta`, and responses may come back
    either as plain JSON or as a server-sent event stream.
    """

    def __init__(
        self,
        name: str,
        url: str,
        auth: httpx.Auth | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure the client; no connection is made until `connect`.

        Args:
            name: Server name, used to namespace its tools.
            url: Endpoint of the MCP server.
            auth: Optional httpx auth scheme applied to every request.
            transport: Optional httpx transport; the network when `None`.
                Tests pass an `httpx.MockTransport`.
        """
        self._name = name
        self._client: httpx.AsyncClient | None = None
        self._url = url
        self._auth = auth
        self._transport = transport
        self._logger = logging.getLogger(__name__)
        self._protocol_version: str = "2026-07-28"
        self._session_id: str | None = None
        self._next_id = 0

    @property
    def name(self) -> str:
        """Server name, used to namespace its tools."""
        return self._name

    async def connect(self) -> None:
        """Start the server connection and perform the MCP handshake.

        Raises:
            McpUnavailableError: The server cannot be started or reached.
        """
        self._client = httpx.AsyncClient(
            base_url=self._url,
            auth=self._auth,
            transport=self._transport,
            headers=self._headers(),
            timeout=30,
        )
        try:
            await self._initialize()
        except BaseException:
            # Includes cancellation; don't leak the client or mask the original error.
            with contextlib.suppress(Exception):
                await self.aclose()
            raise

    async def _initialize(self) -> None:
        """Discover the server and record its protocol version and session id.

        Raises:
            McpUnavailableError: The discovery request failed or returned an error.
        """
        # Protocol 2026-07-28 is stateless: no initialize/initialized handshake,
        # `server/discover` replaces it, and every request carries its own `_meta`.
        self._logger.info(f"initializing MCP {self._name}: discover phase")
        try:
            resp, resp_json = await self._request("server/discover")
            if "Mcp-Protocol-Version" in resp.headers:
                self._protocol_version = resp.headers["Mcp-Protocol-Version"]
            if "Mcp-Session-Id" in resp.headers:
                self._session_id = resp.headers["Mcp-Session-Id"]
            result = self._result("server/discover", resp_json)
            server_info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
        except Exception as e:
            self._logger.error(f"failed to initialize MCP server at {self._url}: {e}")
            raise McpUnavailableError(
                f"failed to initialize MCP server at {self._url}: {e}"
            ) from e
        self._logger.info(
            f"initialized MCP {self._name}: "
            f"{server_info.get('name')} {server_info.get('version')} "
            f"with protocol version {self._protocol_version} "
            f"and session id {self._session_id}"
        )

    async def aclose(self) -> None:
        """Close the connection. Safe to call twice or before `connect`."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_tools(self) -> Sequence[ToolSpec]:
        """List the tools the server exposes, under their original names.

        Raises:
            McpUnavailableError: The server cannot be reached.
        """
        _, resp_json = await self._request("tools/list")
        # `description` and `annotations` are optional; an unannotated tool is
        # assumed to have side effects, as the spec's `readOnlyHint` default says.
        return [
            ToolSpec(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=tool["inputSchema"],
                requires_confirmation=not tool.get("annotations", {}).get(
                    "readOnlyHint", False
                ),
            )
            for tool in self._result("tools/list", resp_json)["tools"]
        ]

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        """Call a tool and return its content flattened to text.

        Args:
            name: The tool's original name, as returned by `list_tools`.
            arguments: The arguments, matching the tool's parameter schema.

        Raises:
            McpUnavailableError: The server cannot be reached.
            McpToolError: The server reported that the tool failed.
        """
        _, resp_json = await self._request(
            "tools/call", params={"name": name, "arguments": dict(arguments)}
        )
        # Protocol errors (unknown tool, invalid arguments) come back as a JSON-RPC
        # `error`; failures during execution as a result flagged `isError`.
        if "error" in resp_json:
            error = resp_json["error"]
            raise McpToolError(f"{self._name}: {name} failed: {error.get('message')}")
        result = resp_json["result"]
        text = "\n".join(c["text"] for c in result["content"] if c["type"] == "text")
        if result.get("isError"):
            raise McpToolError(f"{self._name}: {name} failed: {text}")
        return text

    def _result(self, method: str, message: Mapping[str, Any]) -> dict[str, Any]:
        """Return the `result` of a JSON-RPC response.

        Args:
            method: The JSON-RPC method the response answers, for the error message.
            message: The decoded JSON-RPC response.

        Returns:
            The response's `result` object.

        Raises:
            McpUnavailableError: The server answered with a JSON-RPC `error`, or
                with neither an `error` nor a `result`.
        """
        if "error" in message:
            error = message["error"]
            raise McpUnavailableError(
                f"{self._name}: {method} failed: {error.get('message')}"
            )
        if "result" not in message:
            raise McpUnavailableError(f"{self._name}: {method}: response has no result")
        return message["result"]

    def _require_client(self) -> httpx.AsyncClient:
        """Return the HTTP client, failing if `connect` was not called.

        Raises:
            McpUnavailableError: The client is not connected.
        """
        if self._client is None:
            raise McpUnavailableError(f"{self._name}: not connected")
        return self._client

    def _headers(self) -> dict[str, str]:
        """Return the protocol headers shared by every request."""
        headers = {
            "Accept": "application/json, text/event-stream",
            "Mcp-Protocol-Version": self._protocol_version,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _build_payload(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> dict:
        """Build a JSON-RPC request with a fresh id and the per-request `_meta`.

        Args:
            method: The JSON-RPC method name.
            params: The method parameters, if any.

        Returns:
            The JSON-RPC payload, ready to be sent.
        """
        self._next_id += 1
        return {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": {
                **(params or {}),
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": self._protocol_version,
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "sensai",
                        "version": "0.1.0",
                    },
                },
            },
        }

    async def _request(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> tuple[httpx.Response, dict]:
        """Send a JSON-RPC request and return the matching response.

        Handles both `application/json` and `text/event-stream` replies; in a
        stream, notifications are skipped until the response with our id arrives.

        Args:
            method: The JSON-RPC method name.
            params: The method parameters, if any.

        Returns:
            The HTTP response and its decoded JSON-RPC message.

        Raises:
            McpUnavailableError: The request failed at the transport level or
                timed out, the server returned an HTTP error, an unexpected content
                type, malformed JSON, or a stream that ended without a response.
        """
        payload = self._build_payload(method, params)
        headers = {**self._headers(), "Mcp-Method": method}
        if params is not None:
            if method in {"tools/call", "prompts/get"}:
                headers["Mcp-Name"] = str(params["name"])
            elif method == "resources/read":
                headers["Mcp-Name"] = str(params["uri"])
        try:
            async with self._require_client().stream(
                "POST", "", json=payload, headers=headers
            ) as resp:
                self._logger.info(f"request to MCP {self._name}: {payload}")
                if resp.is_error:
                    body = (await resp.aread()).decode(errors="replace")
                    raise McpUnavailableError(
                        f"{self._name}: HTTP {resp.status_code} for {method}: {body}"
                    )
                ctype = resp.headers.get("content-type", "")
                if ctype.startswith("application/json"):
                    return resp, json.loads(await resp.aread())
                if ctype.startswith("text/event-stream"):
                    data: list[str] = []
                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            data.append(line[5:].lstrip())
                        elif line == "" and data:  # end of one SSE event
                            msg = json.loads("\n".join(data))
                            data.clear()
                            if msg.get("id") == payload["id"]:
                                return resp, msg  # our response; skip notifications
                    raise McpUnavailableError("stream ended without a response")
                raise McpUnavailableError(f"unexpected content-type {ctype!r}")
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            raise McpUnavailableError(f"{self._name}: {method} failed: {e}") from e
