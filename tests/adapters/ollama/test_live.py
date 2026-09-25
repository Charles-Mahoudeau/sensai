"""Opt-in tests against a real Ollama server.

Skipped unless `SENSAI_LIVE_OLLAMA=1`, so CI and offline runs are unaffected.
`SENSAI_LIVE_MODEL` (default `llama3.2:3b`) must be a model that supports tools,
and `SENSAI_LIVE_URL` (default `http://localhost:11434`) points at the server.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from sensai.adapters.ollama import OllamaChat
from sensai.core.models.llm import (
    ChatDone,
    ChatOptions,
    Message,
    TextDelta,
    ToolCallRequest,
)
from sensai.core.models.tools import ToolSpec
from sensai.core.ports import ModelNotFoundError

pytestmark = pytest.mark.skipif(
    os.environ.get("SENSAI_LIVE_OLLAMA") != "1",
    reason="set SENSAI_LIVE_OLLAMA=1 to test against a real Ollama server",
)

URL = os.environ.get("SENSAI_LIVE_URL", "http://localhost:11434")
MODEL = os.environ.get("SENSAI_LIVE_MODEL", "llama3.2:3b")
OPTIONS = ChatOptions(temperature=0.0, seed=1)
WEATHER = ToolSpec(
    "get_weather",
    "Get the weather of a city",
    {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(10, read=None))


def test_a_real_answer_streams_and_ends_with_chat_done() -> None:
    """The model answers in several events and the last one is ChatDone."""

    async def run() -> list[object]:
        async with _client() as client:
            chat = OllamaChat(client, URL, MODEL)
            history = [Message.user("Say hello in one short sentence.")]
            return [event async for event in chat.chat(history, options=OPTIONS)]

    events = asyncio.run(run())

    assert any(isinstance(event, TextDelta) for event in events)
    assert isinstance(events[-1], ChatDone)
    assert events[-1].usage.completion_tokens > 0


def test_a_real_tool_call_is_requested_with_an_id() -> None:
    """The model asks for the weather tool and the call has an id."""

    async def run() -> list[object]:
        async with _client() as client:
            chat = OllamaChat(client, URL, MODEL)
            history = [Message.user("What is the weather in Paris? Use the tool.")]
            return [
                event
                async for event in chat.chat(history, tools=[WEATHER], options=OPTIONS)
            ]

    requests = [
        event for event in asyncio.run(run()) if isinstance(event, ToolCallRequest)
    ]

    assert requests
    assert requests[0].call.name == "get_weather"
    assert requests[0].call.id


def test_an_unknown_model_is_model_not_found() -> None:
    """Ollama's 404 is translated to the port's error."""

    async def run() -> None:
        async with _client() as client:
            chat = OllamaChat(client, URL, "definitely-not-a-model:1b")
            _ = [event async for event in chat.chat([Message.user("Hi")])]

    with pytest.raises(ModelNotFoundError):
        asyncio.run(run())
