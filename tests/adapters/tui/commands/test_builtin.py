"""Tests for the built-in slash commands, run against a fake front-end."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.builtin import default_registry
from sensai.adapters.tui.commands.builtin.clear import CLEARED_HINT
from sensai.adapters.tui.commands.builtin.logs import NO_LOGS_HINT
from sensai.adapters.tui.log_buffer import LogBuffer
from sensai.adapters.tui.panels import (
    LogsPanel,
    McpPanel,
    SessionsPanel,
    ToolsPanel,
    UsagePanel,
)
from sensai.core.agent.re_act import ReActAgent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import Message, ThinkingEffort
from sensai.core.models.persona import Persona, PersonaEntry, PersonaSection
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import StorageError
from sensai.core.tools.registry import ToolRegistry
from tests.adapters.tui.commands.test_registry import FakeContext
from tests.core.test_engine import ScriptedRunner, WaitingRunner
from tests.fakes import FakeLLM, InMemoryPersonaSource, InMemorySessionStore

if TYPE_CHECKING:
    from sensai.core.models.memory import Session


def test_default_registry_lists_the_builtins_in_menu_order() -> None:
    """The menu lists the builtins, /logs after /usage and /exit last."""
    assert [spec.name for spec in default_registry().specs()] == [
        "/clear",
        "/effort",
        "/persona",
        "/mcp",
        "/tools",
        "/usage",
        "/logs",
        "/sessions",
        "/exit",
    ]


def test_clear_runs_the_hook_before_forgetting_the_conversation() -> None:
    """The hook still sees the history; afterwards everything is cleared."""
    engine = Engine(
        ScriptedRunner(()), Pipeline(), EventBus(), history=[Message.user("Hi")]
    )
    context = FakeContext(engine)
    seen: list[int] = []

    async def on_clear() -> None:
        seen.append(len(engine.history))

    asyncio.run(default_registry(on_clear=on_clear).run("/clear", context))

    assert seen == [1]
    assert engine.history == ()
    assert context.cleared == 1
    assert context.hints == [CLEARED_HINT]


def test_effort_sets_shows_and_rejects_levels() -> None:
    """A level is applied and shown; bare shows it; a bad one lists the choices."""
    engine = Engine(ReActAgent(FakeLLM([]), ToolRegistry()), Pipeline(), EventBus())
    context = FakeContext(engine)
    registry = default_registry()

    async def run() -> None:
        await registry.run("/effort HIGH", context)
        await registry.run("/effort", context)
        await registry.run("/effort bogus", context)

    asyncio.run(run())

    assert engine.thinking_effort is ThinkingEffort.HIGH
    assert context.refreshed == 1
    assert context.hints == [
        "Thinking effort: Deep thinking",
        "Thinking effort: Deep thinking",
        "Unknown effort 'bogus'. Use one of: none, low, medium, high, ultra",
    ]


def test_effort_shows_what_the_runner_really_uses() -> None:
    """A runner that can't reason stays at No thinking."""
    context = FakeContext()

    asyncio.run(default_registry().run("/effort ultra", context))

    assert context.hints == ["Thinking effort: No thinking"]


def test_exit_and_its_alias_close_the_front_end() -> None:
    """/exit and /quit both exit."""
    for text in ("/exit", "/quit"):
        context = FakeContext()
        asyncio.run(default_registry().run(text, context))
        assert context.exited


def test_mcp_tools_and_usage_open_their_panels() -> None:
    """/mcp, /tools and /usage each open their panel in place of the prompt."""
    context = FakeContext()
    registry = default_registry()

    async def run() -> None:
        await registry.run("/mcp", context)
        await registry.run("/tools", context)
        await registry.run("/usage", context)

    asyncio.run(run())

    assert [type(panel) for panel in context.panels] == [
        McpPanel,
        ToolsPanel,
        UsagePanel,
    ]


def test_sessions_and_its_alias_open_the_sessions_panel() -> None:
    """/sessions and /chats both list the stored sessions, titles included."""

    async def run(text: str) -> FakeContext:
        store = InMemorySessionStore()
        await store.create_session(model="m", title="Greeting")
        engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), sessions=store)
        context = FakeContext(engine)
        await default_registry().run(text, context)
        return context

    for text in ("/sessions", "/chats"):
        context = asyncio.run(run(text))
        [panel] = context.panels
        assert isinstance(panel, SessionsPanel)
        assert [s.title for s in panel._sessions] == ["Greeting"]


def _persona(name: str) -> Persona:
    section = PersonaSection("identity", (PersonaEntry("role", name),))
    return Persona(name, (section,))


def test_persona_switches_shows_and_rejects_names() -> None:
    """A name is switched to; bare shows it; an unknown one is explained."""
    engine = Engine(
        ScriptedRunner(()),
        Pipeline(),
        EventBus(),
        personas=InMemoryPersonaSource(_persona("sensei"), _persona("pirate")),
    )
    context = FakeContext(engine)
    registry = default_registry(persona_names=engine.persona_names)

    async def run() -> None:
        await registry.run("/persona", context)
        await registry.run("/persona pirate", context)
        await registry.run("/persona ghost", context)

    asyncio.run(run())

    assert engine.persona == _persona("pirate")
    assert context.refreshed == 1
    assert context.hints == [
        "Persona: none (available: pirate, sensei)",
        "Persona: pirate (available: pirate, sensei)",
        "Unknown persona 'ghost'",
    ]


def test_persona_completes_the_names_of_the_engine() -> None:
    """The completions follow the personas the engine can switch to."""
    source = InMemoryPersonaSource(_persona("sensei"))
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), personas=source)
    registry = default_registry(persona_names=engine.persona_names)

    source.personas["pirate"] = _persona("pirate")

    assert [item.label for item in registry.complete("/persona ")] == [
        "pirate",
        "sensei",
    ]


def test_persona_is_refused_while_a_submission_runs() -> None:
    """Switching under a running turn is explained, not raised."""

    async def run() -> FakeContext:
        engine = Engine(
            WaitingRunner(),
            Pipeline(),
            EventBus(),
            personas=InMemoryPersonaSource(_persona("sensei")),
        )
        context = FakeContext(engine)
        submission_id = engine.submit("Hello")

        await default_registry().run("/persona sensei", context)

        engine.interrupt(submission_id)
        await asyncio.sleep(0)
        return context

    context = asyncio.run(run())

    assert context.hints == ["A submission is already in progress."]
    assert context.refreshed == 0


def test_sessions_reports_a_store_failure_as_a_hint() -> None:
    """A store that cannot be read gives a hint, not a crash or a panel."""

    class _BrokenStore(InMemorySessionStore):
        async def list_sessions(self, *, limit: int | None = 50) -> list[Session]:
            raise StorageError("disk gone")

    context = FakeContext(
        Engine(ScriptedRunner(()), Pipeline(), EventBus(), sessions=_BrokenStore())
    )

    asyncio.run(default_registry().run("/sessions", context))

    assert context.panels == []
    assert context.hints == ["Could not read the sessions: disk gone"]


def test_resuming_a_session_loads_it_and_shows_it_under_its_title() -> None:
    """The chosen session's messages go to the engine and the transcript."""
    store = InMemorySessionStore()
    messages = [Message.user("hi"), Message.assistant("hello")]

    async def on_resume(session_id: int) -> list[Message]:
        del session_id
        return messages

    async def run() -> FakeContext:
        session = await store.create_session(model="m", title="Greeting")
        engine = Engine(ScriptedRunner(()), Pipeline(), EventBus(), sessions=store)
        context = FakeContext(engine)
        await default_registry(on_resume=on_resume).run("/sessions", context)
        [panel] = context.panels
        assert isinstance(panel, SessionsPanel)
        assert panel._on_select is not None
        await panel._on_select(session)
        return context

    context = asyncio.run(run())

    assert context.engine.history == tuple(messages)
    assert context.sessions_shown == [("Greeting", tuple(messages))]


def test_resuming_fails_with_a_hint_and_keeps_the_conversation() -> None:
    """A store error leaves the engine history and the transcript alone."""
    store = InMemorySessionStore()

    async def on_resume(session_id: int) -> list[Message]:
        raise StorageError(f"no session {session_id}")

    async def run() -> FakeContext:
        session = await store.create_session(model="m")
        engine = Engine(
            ScriptedRunner(()),
            Pipeline(),
            EventBus(),
            history=[Message.user("keep")],
            sessions=store,
        )
        context = FakeContext(engine)
        await default_registry(on_resume=on_resume).run("/chats", context)
        [panel] = context.panels
        assert isinstance(panel, SessionsPanel)
        assert panel._on_select is not None
        await panel._on_select(session)
        return context

    context = asyncio.run(run())

    assert context.engine.history == (Message.user("keep"),)
    assert context.sessions_shown == []
    assert len(context.hints) == 1
    assert context.hints[0].startswith("Could not resume the session")


def test_logs_opens_the_panel_on_the_buffer() -> None:
    """/logs shows the buffered records in a panel."""
    context = FakeContext(Engine(ScriptedRunner(()), Pipeline(), EventBus()))
    buffer = LogBuffer()

    asyncio.run(default_registry(log_buffer=buffer).run("/logs", context))

    (panel,) = context.panels
    assert isinstance(panel, LogsPanel)
    assert panel._buffer is buffer


def test_logs_without_a_buffer_says_so() -> None:
    """Without a buffer wired, /logs only explains why."""
    context = FakeContext(Engine(ScriptedRunner(()), Pipeline(), EventBus()))

    asyncio.run(default_registry().run("/logs", context))

    assert context.panels == []
    assert context.hints == [NO_LOGS_HINT]
