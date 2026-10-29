"""Tests for ReAct calls to persistent-memory tools."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from sensai.core.agent.events import ToolRunStarted, TurnCompleted
from sensai.core.agent.memory_recall import MemoryRecall
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, TextDelta
from sensai.core.tools.builtin import memory
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM
from tests.fakes.memory import InMemoryMemoryStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.events import AgentEvent

READY = '{"thought": "All known.", "action": "answer"}'


async def _collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Collect all events from an agent run."""
    return [event async for event in events]


def _agent(llm: FakeLLM, store: InMemoryMemoryStore, *, limit: int = 20) -> ReActAgent:
    """Build a ReAct agent using the shared persistent-memory store."""
    registry = ToolRegistry()
    memory.register_self(registry, store)
    return ReActAgent(llm, registry, memory_recall=MemoryRecall(store, limit=limit))


def _step(thought: str, action: str, **arguments: Any) -> list[TextDelta]:
    """Script a step calling a tool, as the model writes it under the schema."""
    data = {"thought": thought, "action": action, "arguments": arguments}
    return [TextDelta(json.dumps(data))]


async def _partly_shown_store() -> InMemoryMemoryStore:
    """A store with more memories than a recall limit of 1 shows."""
    store = InMemoryMemoryStore()
    await store.create(name="car", type="preference", description="BMW")
    await store.create(name="language", type="preference", description="Rust")
    return store


def _offered(llm: FakeLLM, request: int) -> set[str]:
    """The tools a step request lets the model call."""
    options = llm.options[request]
    assert options is not None
    assert options.response_schema is not None
    actions = {
        branch["properties"]["action"]["const"]
        for branch in options.response_schema["anyOf"]
    }
    return actions - {"answer"}


def test_react_agent_maintains_and_recalls_memory_across_sessions() -> None:
    """A fact is created, corrected, then shown to a new agent session."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        create_llm = FakeLLM(
            [
                _step(
                    "I should store this durable preference.",
                    "memory_create",
                    name="preferred language",
                    type="preference",
                    description="The user prefers Python.",
                ),
                [TextDelta(READY)],
                [TextDelta("I will use Python in future examples.")],
            ]
        )
        await _collect(
            _agent(create_llm, store).run((Message.user("I prefer Python."),))
        )

        created = (await store.find(query="preferred language"))[0]
        assert created.description == "The user prefers Python."
        # Nothing was stored yet: no memory block, and nothing to search.
        assert [m.role for m in create_llm.messages[0]] == ["user", "user"]
        assert "memory_read" not in _offered(create_llm, 0)

        update_llm = FakeLLM(
            [
                _step(
                    "The existing preference is contradicted, so I should update it.",
                    "memory_update",
                    memory_id=created.id,
                    description="The user now prefers Rust.",
                ),
                [TextDelta(READY)],
                [TextDelta("I will use Rust in future examples.")],
            ]
        )
        await _collect(
            _agent(update_llm, store).run((Message.user("I now prefer Rust."),))
        )
        system = update_llm.messages[0][0]
        assert system.role == "system"
        assert "- preferred language: The user prefers Python." in system.content

        # A new session, as after /clear: only the stored memory knows the fact.
        recall_llm = FakeLLM(
            [
                [TextDelta(READY)],
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
        for request in recall_llm.messages:
            assert "The user now prefers Rust." in request[0].content
            assert not any(m.role == "tool" or m.tool_calls for m in request)
        assert not any(isinstance(e, ToolRunStarted) for e in events)
        assert events[-1] == TurnCompleted(
            [Message.assistant("Your preferred language is Rust.")]
        )

    asyncio.run(run())


def test_memories_extend_the_engine_system_message() -> None:
    """The model still gets one system message: the engine's, then the memories."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        await store.create(
            name="voiture préférée",
            type="préférence",
            description="Préfère les voitures BMW.",
        )
        llm = FakeLLM([[TextDelta(READY)], [TextDelta("BMW.")]])

        await _collect(
            _agent(llm, store).run(
                (Message.system("SYSTEM"), Message.user("Ma voiture préférée ?"))
            )
        )

        for request in llm.messages:
            (system,) = [m for m in request if m.role == "system"]
            assert system == request[0]
            assert system.content.startswith("SYSTEM\n\nWhat you remember")
            assert "voiture préférée: Préfère les voitures BMW." in system.content

    asyncio.run(run())


def test_memory_read_is_offered_only_when_some_memories_are_not_shown() -> None:
    """Past the recall limit, a search can still find what the block left out."""

    async def run() -> tuple[set[str], set[str]]:
        store = InMemoryMemoryStore()
        await store.create(name="car", type="preference", description="BMW")
        complete = FakeLLM([[TextDelta("Thinking.")], [TextDelta("Answer.")]])
        await _collect(_agent(complete, store).run((Message.user("Hi"),)))

        await store.create(name="language", type="preference", description="Rust")
        partial = FakeLLM([[TextDelta("Thinking.")], [TextDelta("Answer.")]])
        await _collect(_agent(partial, store, limit=1).run((Message.user("Hi"),)))
        return _offered(complete, 0), _offered(partial, 0)

    complete, partial = asyncio.run(run())

    assert "memory_read" not in complete
    assert {"memory_read", "memory_update"} <= partial


def test_memories_are_not_shown_when_the_tools_are_disabled() -> None:
    """With the tools off (`--no-tools`), memory stays out of the conversation."""

    async def run() -> FakeLLM:
        store = InMemoryMemoryStore()
        await store.create(name="car", type="preference", description="BMW")
        llm = FakeLLM([[TextDelta(READY)], [TextDelta("Hello.")]])
        registry = ToolRegistry()
        memory.register_self(registry, store)
        registry.set_all_enabled(enabled=False)
        agent = ReActAgent(llm, registry, memory_recall=MemoryRecall(store))
        await _collect(agent.run((Message.user("Hi"),)))
        return llm

    llm = asyncio.run(run())

    assert not any(m.role == "system" for request in llm.messages for m in request)


def test_react_agent_shows_no_memory_when_nothing_is_stored() -> None:
    """A public question with nothing stored gets no memory in its context."""

    async def run() -> None:
        llm = FakeLLM(
            [
                [TextDelta('{"thought": "Public knowledge.", "action": "answer"}')],
                [TextDelta("It is a public figure.")],
            ]
        )
        events = await _collect(
            _agent(llm, InMemoryMemoryStore()).run(
                (Message.user("Who is Sweetie Fox?"),)
            )
        )

        assert not any(
            message.role in ("system", "tool") or message.tool_calls
            for request in llm.messages
            for message in request
        )
        assert events[-1] == TurnCompleted(
            [Message.assistant("It is a public figure.")]
        )

    asyncio.run(run())


def test_react_agent_only_shows_the_answer_as_text() -> None:
    """Thoughts and calls never reach the answer: only the last reply does."""

    async def run() -> None:
        llm = FakeLLM(
            [
                _step("Let me look.", "memory_read", query="x"),
                [TextDelta(READY)],
                [TextDelta("Final answer.")],
            ]
        )
        events = await _collect(
            _agent(llm, await _partly_shown_store(), limit=1).run(
                (Message.user("Hello"),)
            )
        )

        shown = "".join(e.text for e in events if isinstance(e, TextDelta))
        assert shown == "Final answer."
        assert events[-1] == TurnCompleted([Message.assistant("Final answer.")])

    asyncio.run(run())


def test_react_agent_answers_instead_of_repeating_a_tool_call() -> None:
    """The same call twice in a turn runs once, then the agent answers."""

    async def run() -> None:
        llm = FakeLLM(
            [
                _step("Let me look.", "memory_read", query="zzz"),
                _step("Let me look again.", "memory_read", query="zzz"),
                [TextDelta("Nothing is stored.")],
            ]
        )
        events = await _collect(
            _agent(llm, await _partly_shown_store(), limit=1).run(
                (Message.user("Hello"),)
            )
        )

        assert sum(isinstance(e, ToolRunStarted) for e in events) == 1
        assert events[-1] == TurnCompleted([Message.assistant("Nothing is stored.")])

    asyncio.run(run())
