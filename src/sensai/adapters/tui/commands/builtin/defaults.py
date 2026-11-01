"""The registry holding every built-in slash command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.builtin import (
    clear,
    effort,
    exit_,
    logs,
    mcp,
    persona,
    sessions,
    tools,
    usage,
)
from sensai.adapters.tui.commands.registry import CommandRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from sensai.adapters.tui.log_buffer import LogBuffer
    from sensai.core.models import Message


def default_registry(
    *,
    on_clear: Callable[[], Awaitable[None]] | None = None,
    on_resume: Callable[[int], Awaitable[Sequence[Message]]] | None = None,
    persona_names: Callable[[], Sequence[str]] = tuple,
    log_buffer: LogBuffer | None = None,
) -> CommandRegistry:
    """Build a registry holding every built-in command.

    Args:
        on_clear: Awaited by /clear before the engine history is cleared.
        on_resume: Awaited by /sessions with the session chosen; returns its
            messages. /sessions only lists the sessions if None.
        persona_names: The personas /persona completes, asked on every
            completion; none by default.
        log_buffer: The records /logs shows; /logs only says they are not
            collected if None.

    Returns:
        The registry, in the order the commands are listed in the menu.
    """
    registry = CommandRegistry()
    clear.register_self(registry, on_clear=on_clear)
    effort.register_self(registry)
    persona.register_self(registry, names=persona_names)
    mcp.register_self(registry)
    tools.register_self(registry)
    usage.register_self(registry)
    logs.register_self(registry, buffer=log_buffer)
    sessions.register_self(registry, on_resume=on_resume)
    exit_.register_self(registry)
    return registry
