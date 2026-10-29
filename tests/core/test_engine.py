"""Tests for the public Engine facade."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from sensai.core.agent.events import TurnCompleted
from sensai.core.agent.re_act import ReActAgent
from sensai.core.engine import Engine
from sensai.core.errors import SubmissionInProgressError
from sensai.core.events import (
    Done,
    EventBus,
    MessageCompleted,
    MessageStarted,
    ThinkingGenerated,
    TokenGenerated,
)
from sensai.core.model_memory import ModelMemory
from sensai.core.models import (
    McpServerStatus,
    Message,
    TextDelta,
    ThinkingEffort,
    ToolCall,
)
from sensai.core.models.llm import (
    LoadedModel,
    ThinkingDelta,
    ToolCallRequest,
    UsageTotals,
)
from sensai.core.models.persona import Persona, PersonaEntry, PersonaSection
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import PersonaNotFoundError
from sensai.core.tools.builtin import web_search
from sensai.core.tools.registry import ToolRegistry
from sensai.core.usage import UsageMeter
from tests.fakes import (
    FakeLLM,
    FakeModelMonitor,
    InMemoryPersonaSource,
    InMemorySessionStore,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from sensai.core.agent.events import AgentEvent


class ScriptedRunner:
    """Stream a fixed answer for an Engine test."""

    def __init__(self, events: tuple[AgentEvent, ...]) -> None:
        """Store the events streamed by the runner."""
        self._events = events

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Yield the configured events in order."""
        del messages
        for event in self._events:
            yield event


class WaitingRunner:
    """Wait forever so the Engine can interrupt generation."""

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Wait until the surrounding task is cancelled."""
        del messages
        await asyncio.Event().wait()
        yield TurnCompleted([])


def test_submit_streams_public_events() -> None:
    """A submitted message is translated into public Engine events."""

    async def run() -> None:
        bus = EventBus()
        engine = Engine(
            ScriptedRunner(
                (
                    TextDelta("Bon"),
                    TextDelta("jour"),
                    TurnCompleted([Message.assistant("Bonjour")]),
                )
            ),
            Pipeline(),
            bus,
        )
        events = engine.subscribe()

        submission_id = engine.submit("Hello")

        assert await anext(events) == MessageStarted(submission_id)
        assert await anext(events) == TokenGenerated(submission_id, "Bon")
        assert await anext(events) == TokenGenerated(submission_id, "jour")
        assert await anext(events) == MessageCompleted(
            submission_id, Message.assistant("Bonjour")
        )
        assert await anext(events) == Done(submission_id)
        await events.aclose()

    asyncio.run(run())


def test_thinking_is_published_as_its_own_event() -> None:
    """Reasoning fragments are relayed apart from the answer tokens."""

    async def run() -> None:
        engine = Engine(
            ScriptedRunner(
                (
                    ThinkingDelta("Hmm"),
                    TextDelta("Hi"),
                    TurnCompleted([Message.assistant("Hi")]),
                )
            ),
            Pipeline(),
            EventBus(),
        )
        events = engine.subscribe()

        submission_id = engine.submit("Hello")

        assert await anext(events) == MessageStarted(submission_id)
        assert await anext(events) == ThinkingGenerated(submission_id, "Hmm")
        assert await anext(events) == TokenGenerated(submission_id, "Hi")
        await events.aclose()

    asyncio.run(run())


def test_interrupt_ends_a_running_submission() -> None:
    """Interrupting a submission closes its event stream with Done."""

    async def run() -> None:
        bus = EventBus()
        engine = Engine(WaitingRunner(), Pipeline(), bus)
        events = engine.subscribe()

        submission_id = engine.submit("Hello")
        assert await anext(events) == MessageStarted(submission_id)

        engine.interrupt(submission_id)

        assert await anext(events) == Done(submission_id)
        await events.aclose()

    asyncio.run(run())


def test_model_receives_exactly_one_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engine adds the system message; the agent doesn't add another one."""

    async def search(args: Mapping[str, Any]) -> str:
        del args
        return "result"

    monkeypatch.setattr(web_search, "_web_search", search)
    llm = FakeLLM(
        [
            [TextDelta("I need data.")],
            [ToolCallRequest(ToolCall("web_search", {"query": "q"}, id="c1"))],
            [TextDelta('{"thought": "All known.", "ready": true}')],
            [TextDelta("Done.")],
        ]
    )

    tools = ToolRegistry()
    web_search.register_self(tools)

    async def run() -> None:
        agent = ReActAgent(llm, tools)
        engine = Engine(agent, Pipeline(), EventBus(), system_prompt="SYSTEM")
        events = engine.subscribe()
        engine.submit("Hello")
        async for event in events:
            if isinstance(event, Done):
                break
        await events.aclose()

    asyncio.run(run())

    assert len(llm.messages) == 4
    for request in llm.messages:
        assert [m.content for m in request if m.role == "system"] == ["SYSTEM"]
        assert request[0].role == "system"


class EffortRunner(ScriptedRunner):
    """A scripted runner exposing a settable thinking effort."""

    def __init__(self) -> None:
        """Start with no events and the default effort."""
        super().__init__(())
        self.thinking_effort = ThinkingEffort.NONE


def test_clear_forgets_the_history() -> None:
    """Clearing empties the history the next submission starts from."""
    engine = Engine(
        ScriptedRunner(()), Pipeline(), EventBus(), history=[Message.user("Hi")]
    )

    engine.clear()

    assert engine.history == ()


def test_clear_is_refused_while_a_submission_runs() -> None:
    """The history can't be cleared under a running turn."""

    async def run() -> None:
        engine = Engine(WaitingRunner(), Pipeline(), EventBus())
        submission_id = engine.submit("Hello")

        with pytest.raises(SubmissionInProgressError):
            engine.clear()

        engine.interrupt(submission_id)
        await asyncio.sleep(0)

    asyncio.run(run())


def test_thinking_effort_cycles_and_reaches_the_runner() -> None:
    """Cycling the effort wraps after the highest and updates the runner."""
    runner = EffortRunner()
    runner.thinking_effort = ThinkingEffort.HIGH
    engine = Engine(runner, Pipeline(), EventBus())
    assert engine.thinking_effort is ThinkingEffort.HIGH

    assert engine.cycle_thinking_effort() is ThinkingEffort.ULTRA
    assert runner.thinking_effort is ThinkingEffort.ULTRA
    assert engine.cycle_thinking_effort() is ThinkingEffort.NONE
    assert runner.thinking_effort is ThinkingEffort.NONE


def test_thinking_effort_works_with_runners_that_do_not_support_it() -> None:
    """Without runner support the effort stays NONE and cycling is a no-op."""
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus())

    assert engine.cycle_thinking_effort() is ThinkingEffort.NONE


def test_engine_lists_and_toggles_its_tools() -> None:
    """Front-ends see every tool and toggle them through the engine."""
    registry = ToolRegistry()
    web_search.register_self(registry)
    status = McpServerStatus("github", "https://mcp.test/", connected=False)
    engine = Engine(
        ScriptedRunner(()),
        Pipeline(),
        EventBus(),
        tools=registry,
        mcp_servers=[status],
    )

    engine.set_tool_enabled("web_search", enabled=False)
    assert [tool.enabled for tool in engine.tools()] == [False]
    assert registry.spec() == ()

    engine.set_tools_enabled(enabled=True)
    assert [tool.enabled for tool in engine.tools()] == [True]
    assert engine.mcp_servers() == (status,)


def test_engine_without_tools_lists_none() -> None:
    """With no registry there is nothing to list, and naming a tool fails."""
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus())

    engine.set_tools_enabled(enabled=False)

    assert engine.tools() == ()
    assert engine.mcp_servers() == ()
    with pytest.raises(KeyError):
        engine.set_tool_enabled("web_search", enabled=False)
    with pytest.raises(KeyError):
        engine.set_tools_enabled(enabled=False, names=["web_search"])


def test_engine_reports_the_loaded_model() -> None:
    """The engine reads the model's memory through its ModelMemory."""
    model = LoadedModel(name="qwen3:8b", size_bytes=10, vram_bytes=8)
    memory = ModelMemory(FakeModelMonitor(model), "qwen3:8b")
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), model_memory=memory)

    assert asyncio.run(engine.loaded_model()) == model


def test_engine_without_model_memory_reports_nothing() -> None:
    """With no monitor the footprint is unknown."""
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus())

    assert asyncio.run(engine.loaded_model()) is None


def test_engine_reports_the_session_usage() -> None:
    """The engine reads the session's usage from its meter, zero without one."""
    meter = UsageMeter(UsageTotals(prompt_tokens=7, calls=1))
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), usage_meter=meter)

    assert engine.usage() == UsageTotals(prompt_tokens=7, calls=1)
    assert Engine(ScriptedRunner(()), Pipeline(), EventBus()).usage() == UsageTotals()


class RecordingRunner:
    """Answer every turn with "ok" and record the messages it was sent."""

    def __init__(self) -> None:
        """Start with no recorded turn."""
        self.turns: list[tuple[Message, ...]] = []

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Record the messages, then complete the turn."""
        self.turns.append(messages)
        yield TurnCompleted([Message.assistant("ok")])


def _persona(name: str, role: str) -> Persona:
    section = PersonaSection("identity", (PersonaEntry("role", role),))
    return Persona(name, (section,))


async def _submit_and_wait(engine: Engine, text: str) -> None:
    events = engine.subscribe()
    engine.submit(text)
    async for event in events:
        if isinstance(event, Done):
            break
    await events.aclose()


def test_switching_persona_keeps_the_history() -> None:
    """A new persona replaces the old one in the system message only."""
    runner = RecordingRunner()
    engine = Engine(
        runner,
        Pipeline(),
        EventBus(),
        system_prompt="BASE",
        profile="PROFILE",
        personas=InMemoryPersonaSource(
            _persona("sensei", "mentor"), _persona("pirate", "pirate")
        ),
    )

    async def run() -> None:
        engine.set_persona("sensei")
        await _submit_and_wait(engine, "Hello")
        engine.set_persona("pirate")
        await _submit_and_wait(engine, "Again")

    asyncio.run(run())

    first, second = runner.turns
    assert first[0] == Message.system("BASE\n\nIdentity:\n- role: mentor\n\nPROFILE")
    assert second[0] == Message.system("BASE\n\nIdentity:\n- role: pirate\n\nPROFILE")
    assert second[1:] == (
        Message.user("Hello"),
        Message.assistant("ok"),
        Message.user("Again"),
    )
    assert engine.persona == _persona("pirate", "pirate")


def test_set_persona_reads_the_current_version() -> None:
    """Switching to a persona again picks up its edits."""
    source = InMemoryPersonaSource(_persona("sensei", "mentor"))
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), personas=source)
    engine.set_persona("sensei")

    source.personas["sensei"] = _persona("sensei", "strict mentor")

    assert engine.set_persona("sensei") == _persona("sensei", "strict mentor")


def test_persona_names_come_from_the_source() -> None:
    """The names are read from the source each time they are asked for."""
    source = InMemoryPersonaSource(_persona("sensei", "mentor"))
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), personas=source)

    source.personas["pirate"] = _persona("pirate", "pirate")

    assert engine.persona_names() == ("pirate", "sensei")


def test_unknown_persona_keeps_the_current_one() -> None:
    """A failed switch leaves the active persona as it was."""
    engine = Engine(
        ScriptedRunner(()),
        Pipeline(),
        EventBus(),
        personas=InMemoryPersonaSource(_persona("sensei", "mentor")),
    )
    engine.set_persona("sensei")

    with pytest.raises(PersonaNotFoundError):
        engine.set_persona("ghost")

    assert engine.persona == _persona("sensei", "mentor")


def test_engine_without_personas_has_none() -> None:
    """With no source there is nothing to list, and switching fails."""
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus())

    assert engine.persona is None
    assert engine.persona_names() == ()
    with pytest.raises(PersonaNotFoundError):
        engine.set_persona("sensei")


def test_set_persona_is_refused_while_a_submission_runs() -> None:
    """The persona can't change under a running turn."""

    async def run() -> None:
        engine = Engine(
            WaitingRunner(),
            Pipeline(),
            EventBus(),
            personas=InMemoryPersonaSource(_persona("sensei", "mentor")),
        )
        submission_id = engine.submit("Hello")

        with pytest.raises(SubmissionInProgressError):
            engine.set_persona("sensei")

        engine.interrupt(submission_id)
        await asyncio.sleep(0)

    asyncio.run(run())


def test_list_sessions_reads_the_store_newest_first() -> None:
    """The engine lists what the session store holds."""

    async def run() -> None:
        store = InMemorySessionStore()
        first = await store.create_session(model="m", title="First")
        second = await store.create_session(model="m", title="Second")
        engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), sessions=store)

        listed = await engine.list_sessions()

        assert {s.id for s in listed} == {first.id, second.id}

    asyncio.run(run())


def test_list_sessions_is_empty_without_a_store() -> None:
    """No store configured means no sessions."""
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus())

    assert asyncio.run(engine.list_sessions()) == ()
