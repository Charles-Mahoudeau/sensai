"""Tests for ReAct calls to persistent-memory tools."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sensai.core.agent.events import TurnCompleted
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


def _agent(llm: FakeLLM, store: InMemoryMemoryStore) -> ReActAgent:
    """Build a ReAct agent using the shared persistent-memory store."""
    registry = ToolRegistry()
    memory.register_self(registry, store)
    return ReActAgent(llm, registry)


def test_react_agent_maintains_and_recalls_memory_across_sessions() -> None:
    """A fact is created, corrected, then supplied to a new agent session."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        create_llm = FakeLLM(
            [
                [TextDelta("I should store this durable preference.")],
                [
                    ToolCallRequest(
                        ToolCall(
                            "memory_create",
                            {
                                "name": "preferred language",
                                "type": "preference",
                                "description": "The user prefers Python.",
                            },
                            "create-1",
                        )
                    )
                ],
                [TextDelta("I am ready to answer.")],
                [TextDelta("I will use Python in future examples.")],
            ]
        )
        await _collect(
            _agent(create_llm, store).run((Message.user("I prefer Python."),))
        )

        created = (await store.find(query="preferred language"))[0]
        assert created.description == "The user prefers Python."
        assert any(
            message.role == "tool" and '"records": []' in message.content
            for message in create_llm.messages[0]
        )

        update_llm = FakeLLM(
            [
                [
                    TextDelta(
                        "The existing preference is contradicted, "
                        "so I should update it."
                    )
                ],
                [
                    ToolCallRequest(
                        ToolCall(
                            "memory_update",
                            {
                                "memory_id": created.id,
                                "description": "The user now prefers Rust.",
                            },
                            "update-1",
                        )
                    )
                ],
                [TextDelta("I am ready to answer.")],
                [TextDelta("I will use Rust in future examples.")],
            ]
        )
        await _collect(
            _agent(update_llm, store).run((Message.user("I now prefer Rust."),))
        )
        assert any(
            message.role == "tool" and "The user prefers Python." in message.content
            for message in update_llm.messages[0]
        )

        recall_llm = FakeLLM(
            [
                [TextDelta("I am ready to answer.")],
                [TextDelta("Your preferred language is Rust.")],
            ]
        )
        events = await _collect(
            _agent(recall_llm, store).run(
                (Message.user("Which language do I prefer?"),)
            )
        )

        memories = await store.find()
        assert [(record.name, record.description) for record in memories] == [
            ("preferred language", "The user now prefers Rust.")
        ]
        assert any(
            message.role == "tool" and "The user now prefers Rust." in message.content
            for request in recall_llm.messages
            for message in request
        )
        initial_call = next(
            call
            for message in recall_llm.messages[0]
            for call in message.tool_calls
            if call.name == "memory_read"
        )
        assert initial_call.arguments["query"] == "Which language do I prefer?"
        assert events[-1] == TurnCompleted(
            [Message.assistant("Your preferred language is Rust.")]
        )

    asyncio.run(run())
