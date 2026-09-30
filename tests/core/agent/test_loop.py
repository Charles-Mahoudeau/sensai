"""Tests for the minimal agent loop."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.agent import Agent, AgentError
from sensai.core.agent.events import TurnCompleted
from sensai.core.models import ChatDone, Message, TextDelta
from sensai.core.ports import LLMUnavailableError, ModelNotFoundError
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.events import AgentEvent


HISTORY = (Message.user("Hello"),)


async def _collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Collect every event from an asynchronous stream."""
    return [event async for event in events]


def test_agent_relays_events_and_history() -> None:
    """The agent forwards the complete history and preserves event order."""
    llm = FakeLLM([[TextDelta("Hel"), TextDelta("lo"), ChatDone()]])
    agent = Agent(llm)

    events = asyncio.run(_collect(agent.run(HISTORY)))

    assert events == [
        TextDelta("Hel"),
        TextDelta("lo"),
        TurnCompleted([Message.assistant("Hello")]),
    ]
    assert llm.messages == [list(HISTORY)]


@pytest.mark.parametrize(
    "error",
    [LLMUnavailableError("Ollama is down"), ModelNotFoundError("model is missing")],
)
def test_agent_translates_llm_failures(error: Exception) -> None:
    """Known LLM failures become core errors that the Engine can publish."""
    agent = Agent(FakeLLM([[error]]))

    with pytest.raises(AgentError, match=str(error)) as raised:
        asyncio.run(_collect(agent.run(HISTORY)))

    assert raised.value.__cause__ is error
