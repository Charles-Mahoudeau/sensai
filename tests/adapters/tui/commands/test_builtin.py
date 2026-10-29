"""Tests for the built-in slash commands, run against a fake front-end."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.builtin import default_registry
from sensai.adapters.tui.commands.builtin.clear import CLEARED_HINT
from sensai.adapters.tui.panels import McpPanel, SessionsPanel, ToolsPanel, UsagePanel
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
    """The menu lists the builtins, /sessions after /usage and /exit last."""
    assert [spec.name for spec in default_registry().specs()] == [
        "/clear",
        "/effort",
        "/persona",
        "/mcp",
        "/tools",
        "/usage",
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
        async def list_sessions(self, *, limit: int = 50) -> list[Session]:
            raise StorageError("disk gone")

    context = FakeContext(
        Engine(ScriptedRunner(()), Pipeline(), EventBus(), sessions=_BrokenStore())
    )

    asyncio.run(default_registry().run("/sessions", context))

    assert context.panels == []
    assert context.hints == ["Could not read the sessions: disk gone"]
