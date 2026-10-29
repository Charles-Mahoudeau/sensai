"""Tests for the slash command registry: completion, dispatch and highlighting."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from rich.text import Text

from sensai.adapters.tui.commands import (
    Argument,
    CommandHighlighter,
    CommandRegistry,
    CommandSpec,
    Completion,
)
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.pipeline.base import Pipeline
from tests.core.test_engine import ScriptedRunner

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.adapters.tui.commands import CommandContext
    from sensai.adapters.tui.panels import Panel
    from sensai.core.models import Message


class FakeContext:
    """Record what command handlers do to the front-end."""

    def __init__(self, engine: Engine | None = None) -> None:
        """Start with no hint, no clear and no exit."""
        self._engine = engine or Engine(ScriptedRunner(()), Pipeline(), EventBus())
        self.hints: list[str] = []
        self.cleared = 0
        self.refreshed = 0
        self.exited = False
        self.panels: list[Panel] = []
        self.sessions_shown: list[tuple[str, tuple[Message, ...]]] = []

    @property
    def engine(self) -> Engine:
        """The engine handlers act on."""
        return self._engine

    async def show_hint(self, text: str) -> None:
        """Record the hint."""
        self.hints.append(text)

    async def clear_transcript(self) -> None:
        """Count the clears."""
        self.cleared += 1

    async def show_session(self, title: str, messages: Sequence[Message]) -> None:
        """Record the session shown."""
        self.sessions_shown.append((title, tuple(messages)))

    def refresh_status(self) -> None:
        """Count the refreshes."""
        self.refreshed += 1

    def exit(self) -> None:
        """Record the exit."""
        self.exited = True

    async def open_panel(self, panel: Panel) -> None:
        """Record the panel."""
        self.panels.append(panel)


def _registry(calls: list[str] | None = None) -> CommandRegistry:
    async def record(context: CommandContext, argument: str) -> None:
        del context
        if calls is not None:
            calls.append(argument)

    registry = CommandRegistry()
    registry.register(CommandSpec("/clear", "Clear it"), record)
    registry.register(
        CommandSpec(
            "/effort",
            "Set effort",
            arguments=(Argument("low", "Quick"), Argument("high", "Deep")),
        ),
        record,
    )
    registry.register(CommandSpec("/exit", "Exit", aliases=("/quit",)), record)
    return registry


def test_slash_alone_lists_every_command_but_not_aliases() -> None:
    """Aliases are never offered as completions."""
    assert [item.label for item in _registry().complete("/")] == [
        "/clear",
        "/effort",
        "/exit",
    ]


def test_prefix_filters_commands() -> None:
    """Commands taking arguments complete with a trailing space."""
    assert _registry().complete("/e") == [
        Completion("/effort ", "/effort", "Set effort"),
        Completion("/exit", "/exit", "Exit"),
    ]


def test_arguments_are_completed_after_the_command() -> None:
    """After the command and a space, its matching arguments are offered."""
    registry = _registry()

    assert [item.label for item in registry.complete("/effort ")] == ["low", "high"]
    assert registry.complete("/effort H") == [
        Completion("/effort high", "high", "Deep")
    ]


def test_callable_arguments_are_asked_on_every_completion() -> None:
    """Arguments given as a callable follow values added after registration."""
    names = ["sensei"]
    registry = CommandRegistry()

    async def handler(context: CommandContext, argument: str) -> None:
        del context, argument

    registry.register(
        CommandSpec(
            "/persona",
            "Switch persona",
            arguments=lambda: tuple(Argument(name, "") for name in names),
        ),
        handler,
    )
    assert [item.label for item in registry.complete("/persona ")] == ["sensei"]

    names.append("pirate")

    assert registry.complete("/p") == [
        Completion("/persona ", "/persona", "Switch persona")
    ]
    assert [item.label for item in registry.complete("/persona ")] == [
        "sensei",
        "pirate",
    ]


def test_nothing_is_completed_without_a_match() -> None:
    """Plain text, unknown commands and extra words give no completion."""
    registry = _registry()

    assert registry.complete("hello") == []
    assert registry.complete("/zz") == []
    assert registry.complete("/foo ") == []
    assert registry.complete("/clear ") == []
    assert registry.complete("/effort high now") == []


def test_find_resolves_names_and_aliases() -> None:
    """An alias finds the command it belongs to."""
    registry = _registry()

    assert registry.find("/quit") is registry.find("/exit")
    assert registry.find("/nope") is None


def test_run_dispatches_to_the_handler_with_the_argument() -> None:
    """The handler gets the stripped argument; aliases run the same handler."""
    calls: list[str] = []
    registry = _registry(calls)
    context = FakeContext()

    async def run() -> None:
        assert await registry.run("/effort   high ", context)
        assert await registry.run("/quit", context)

    asyncio.run(run())

    assert calls == ["high", ""]
    assert context.hints == []


def test_run_ignores_plain_text_and_reports_unknown_commands() -> None:
    """Plain text is not handled; an unknown command shows a hint."""
    registry = _registry()
    context = FakeContext()

    async def run() -> None:
        assert not await registry.run("hello /exit", context)
        assert await registry.run("/foo bar", context)

    asyncio.run(run())

    assert context.hints == ["Unknown command /foo"]


def test_names_and_aliases_are_unique() -> None:
    """A name or an alias can't be registered twice."""
    registry = _registry()

    async def handler(context: CommandContext, argument: str) -> None:
        del context, argument

    with pytest.raises(ValueError, match="/exit"):
        registry.register(CommandSpec("/exit", "Again"), handler)
    with pytest.raises(ValueError, match="/quit"):
        registry.register(CommandSpec("/leave", "Leave", aliases=("/quit",)), handler)


@pytest.mark.parametrize("name", ["clear", "/", "/two words", ""])
def test_spec_names_are_validated(name: str) -> None:
    """A command name is a slash followed by a word."""
    with pytest.raises(ValueError, match="Command name"):
        CommandSpec(name, "Bad")


def test_highlighter_styles_only_known_commands() -> None:
    """A known command name is styled; its argument and unknown names are not."""
    highlighter = CommandHighlighter(_registry())

    known = highlighter(Text("/effort high"))
    unknown = highlighter(Text("/foo bar"))

    assert [(span.start, span.end) for span in known.spans] == [(0, 7)]
    assert unknown.spans == []
