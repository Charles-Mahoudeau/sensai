"""Tests for the built-in slash commands, run against a fake front-end."""

from __future__ import annotations

import asyncio

from sensai.adapters.tui.commands.builtin import default_registry
from sensai.adapters.tui.commands.builtin.clear import CLEARED_HINT
from sensai.adapters.tui.panels import McpPanel, ToolsPanel
from sensai.core.agent.re_act import ReActAgent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import Message, ThinkingEffort
from sensai.core.pipeline.base import Pipeline
from sensai.core.tools.registry import ToolRegistry
from tests.adapters.tui.commands.test_registry import FakeContext
from tests.core.test_engine import ScriptedRunner
from tests.fakes import FakeLLM


def test_default_registry_lists_the_builtins_in_menu_order() -> None:
    """The menu shows /clear, /effort, /mcp, /tools and /exit."""
    assert [spec.name for spec in default_registry().specs()] == [
        "/clear",
        "/effort",
        "/mcp",
        "/tools",
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


def test_mcp_and_tools_open_their_panels() -> None:
    """/mcp and /tools each open their panel in place of the prompt."""
    context = FakeContext()
    registry = default_registry()

    async def run() -> None:
        await registry.run("/mcp", context)
        await registry.run("/tools", context)

    asyncio.run(run())

    assert [type(panel) for panel in context.panels] == [McpPanel, ToolsPanel]
