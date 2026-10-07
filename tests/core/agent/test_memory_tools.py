"""Tests for ReAct calls to persistent-memory tools."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from sensai.core.agent.events import ToolRunFinished, TurnCompleted
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, TextDelta, ToolCall
from sensai.core.models.llm import ToolCallRequest
from sensai.core.tools.builtin import memory
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM
from tests.fakes.memory import InMemoryMemoryStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.events import AgentEvent


async def _collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Collect all events from an agent run."""
    return [event async for event in events]


def test_react_agent_creates_memory_through_the_shared_registry() -> None:
    """A scripted model call reaches the injected memory store."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)
        llm = FakeLLM(
            [
                [TextDelta("I should store this preference.")],
                [
                    ToolCallRequest(
                        ToolCall(
                            "memory_create",
                            {
                                "name": "language",
                                "type": "preference",
                                "description": "The user prefers Python.",
                            },
                            "call-memory-create",
                        )
                    )
                ],
                [TextDelta("I am ready to answer.")],
                [TextDelta("I will use Python in future examples.")],
            ]
        )
        agent = ReActAgent(llm, registry)

        events = await _collect(agent.run((Message.user("I prefer Python."),)))

        memories = await store.find()
        assert [(record.name, record.description) for record in memories] == [
            ("language", "The user prefers Python.")
        ]
        assert any(
            isinstance(event, ToolRunFinished)
            and json.loads(event.result.content)["name"] == "language"
            for event in events
        )
        assert events[-1] == TurnCompleted(
            [Message.assistant("I will use Python in future examples.")]
        )

    asyncio.run(run())
