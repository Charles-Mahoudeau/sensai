"""Tests for OllamaChat, using httpx.MockTransport instead of a real server."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx
import pytest

from sensai.adapters.ollama import OllamaChat
from sensai.core.models.llm import (
    ChatDone,
    ChatOptions,
    Message,
    TextDelta,
    ToolCallRequest,
    Usage,
)
from sensai.core.models.tools import ToolCall, ToolSpec
from sensai.core.ports import LLMResponseError, LLMUnavailableError, ModelNotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping, Sequence

    from sensai.core.models.llm import ChatEvent

HISTORY = [Message.user("Hi")]
DONE = {"done": True, "done_reason": "stop", "prompt_eval_count": 5, "eval_count": 2}

type Handler = Callable[[httpx.Request], httpx.Response]


def _ndjson(*chunks: Mapping[str, object]) -> bytes:
    return b"".join(json.dumps(chunk).encode() + b"\n" for chunk in chunks)


def _text(content: str) -> dict[str, object]:
    return {"message": {"role": "assistant", "content": content}, "done": False}


def _collect(
    handler: Handler,
    *,
    tools: Sequence[ToolSpec] = (),
    options: ChatOptions | None = None,
) -> list[ChatEvent]:
    async def run() -> list[ChatEvent]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            chat = OllamaChat(client, "http://ollama:11434", "llama3")
            return [
                event
                async for event in chat.chat(HISTORY, tools=tools, options=options)
            ]

    return asyncio.run(run())


def _reply(body: bytes, status: int = 200) -> Handler:
    return lambda _request: httpx.Response(status, content=body)


def test_text_is_streamed_then_closed_by_chat_done() -> None:
    """Fragments come out in order, followed by one ChatDone with the usage."""
    body = _ndjson(_text("Hel"), _text("lo"), {"message": {"content": ""}, **DONE})

    events = _collect(_reply(body))

    assert events == [
        TextDelta("Hel"),
        TextDelta("lo"),
        ChatDone(Usage(completion_tokens=2, prompt_tokens=5), "stop"),
    ]


def test_tool_call_becomes_a_tool_call_request() -> None:
    """A tool call in the stream is exposed with its name, arguments and id."""
    call = {
        "id": "call_1",
        "function": {"name": "get_weather", "arguments": {"city": "Paris"}},
    }
    body = _ndjson(
        {"message": {"content": "", "tool_calls": [call]}, "done": False}, DONE
    )

    events = _collect(_reply(body))

    assert events[0] == ToolCallRequest(
        ToolCall("get_weather", {"city": "Paris"}, "call_1")
    )
    assert isinstance(events[-1], ChatDone)


def test_request_goes_to_api_chat_with_the_translated_payload() -> None:
    """The adapter posts the model, messages, tools and options as JSON."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_ndjson(DONE))

    _collect(
        handler,
        tools=[ToolSpec("get_weather", "Get the weather")],
        options=ChatOptions(temperature=0.0, max_tokens=64),
    )

    (request,) = seen
    body = json.loads(request.content)
    assert request.method == "POST"
    assert request.url == "http://ollama:11434/api/chat"
    assert body["model"] == "llama3"
    assert body["stream"] is True
    assert body["messages"] == [{"role": "user", "content": "Hi"}]
    assert body["tools"][0]["function"]["name"] == "get_weather"
    assert body["options"] == {"temperature": 0.0, "num_predict": 64}


def test_base_url_trailing_slash_is_ignored() -> None:
    """`http://host/` and `http://host` reach the same endpoint."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, content=_ndjson(DONE))

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            chat = OllamaChat(client, "http://ollama:11434/", "m")
            _ = [event async for event in chat.chat(HISTORY)]

    asyncio.run(run())

    assert seen == ["/api/chat"]


def test_blank_lines_are_ignored() -> None:
    """Empty lines between messages don't break the stream."""
    body = b"\n" + _ndjson(_text("Hi")) + b"\n\n" + _ndjson(DONE)

    assert _collect(_reply(body))[0] == TextDelta("Hi")


def test_nothing_is_read_after_done() -> None:
    """ChatDone is always the last event, even if the server keeps talking."""
    body = _ndjson(DONE, _text("late"))

    events = _collect(_reply(body))

    assert len(events) == 1
    assert isinstance(events[0], ChatDone)


def test_connection_refused_is_unavailable() -> None:
    """A refused connection becomes LLMUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailableError, match="cannot reach Ollama"):
        _collect(handler)


class _DroppedStream(httpx.AsyncByteStream):
    """A response body that dies after its first line."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield _ndjson(_text("Hi"))
        raise httpx.ReadError("connection dropped")


def test_connection_dropped_mid_stream_is_unavailable() -> None:
    """Events already yielded stay valid; the drop is reported afterwards."""
    received: list[ChatEvent] = []

    async def run() -> None:
        transport = httpx.MockTransport(
            lambda _r: httpx.Response(200, stream=_DroppedStream())
        )
        async with httpx.AsyncClient(transport=transport) as client:
            async for event in OllamaChat(client, "http://o", "m").chat(HISTORY):
                received.append(event)  # noqa: PERF401 (keep events seen before the error)

    with pytest.raises(LLMUnavailableError):
        asyncio.run(run())

    assert received == [TextDelta("Hi")]


def test_unknown_model_is_model_not_found() -> None:
    """HTTP 404 becomes ModelNotFoundError with the server's message."""
    body = b'{"error": "model \'nope\' not found"}'

    with pytest.raises(ModelNotFoundError, match="model 'nope' not found"):
        _collect(_reply(body, status=404))


def test_other_http_errors_are_response_errors() -> None:
    """A 500 keeps the server's message in an LLMResponseError."""
    with pytest.raises(LLMResponseError, match="out of memory"):
        _collect(_reply(b'{"error": "out of memory"}', status=500))


def test_error_line_in_the_stream_is_a_response_error() -> None:
    """An `{"error": ...}` line after some text stops the stream."""
    body = _ndjson(_text("Hi"), {"error": "model crashed"})

    with pytest.raises(LLMResponseError, match="model crashed"):
        _collect(_reply(body))


def test_invalid_json_line_is_a_response_error() -> None:
    """A line that is not JSON is reported instead of skipped."""
    with pytest.raises(LLMResponseError, match="invalid JSON"):
        _collect(_reply(b"this is not json\n"))


def test_stream_without_done_is_a_response_error() -> None:
    """The port promises a final ChatDone, so its absence is an error."""
    with pytest.raises(LLMResponseError, match="without a final 'done'"):
        _collect(_reply(_ndjson(_text("Hi"))))
