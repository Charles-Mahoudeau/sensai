"""Tests for the LLM port contract, exercised through FakeLLM."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.models.llm import ChatDone, ChatOptions, Message, TextDelta, Usage
from sensai.core.ports import LLMError, LLMUnavailableError, ModelNotFoundError
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from sensai.core.models.llm import ChatEvent
    from sensai.core.ports import LLM

HISTORY = [Message.user("Hello")]


async def _collect(llm: LLM, messages: list[Message]) -> list[ChatEvent]:
    return [event async for event in llm.chat(messages)]


def test_stream_ends_with_chat_done() -> None:
    """A scripted turn is streamed in order and closed by ChatDone."""
    llm = FakeLLM([[TextDelta("Hel"), TextDelta("lo")]])

    events = asyncio.run(_collect(llm, HISTORY))

    assert events == [TextDelta("Hel"), TextDelta("lo"), ChatDone()]


def test_scripted_chat_done_is_kept() -> None:
    """A turn that already ends with ChatDone isn't given a second one."""
    done = ChatDone(Usage(completion_tokens=2, prompt_tokens=5), "stop")
    llm = FakeLLM([[TextDelta("Hi"), done]])

    events = asyncio.run(_collect(llm, HISTORY))

    assert events == [TextDelta("Hi"), done]


def test_request_is_recorded() -> None:
    """The fake records messages and options so tests can assert on them."""
    llm = FakeLLM([[]])
    options = ChatOptions(temperature=0.0)

    async def run() -> None:
        async for _ in llm.chat(HISTORY, options=options):
            pass

    asyncio.run(run())

    assert llm.messages == [HISTORY]
    assert llm.options == [options]


def test_error_mid_stream_is_raised() -> None:
    """A scripted exception interrupts the stream at its position."""
    llm = FakeLLM([[TextDelta("Hi"), LLMUnavailableError("Ollama is down")]])

    with pytest.raises(LLMUnavailableError, match="Ollama is down"):
        asyncio.run(_collect(llm, HISTORY))


def test_port_errors_share_a_base_class() -> None:
    """Callers can catch every adapter failure with LLMError."""
    assert issubclass(LLMUnavailableError, LLMError)
    assert issubclass(ModelNotFoundError, LLMError)
