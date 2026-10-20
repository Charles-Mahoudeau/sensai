"""The registry holding every built-in slash command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.builtin import (
    clear,
    effort,
    exit_,
    mcp,
    persona,
    tools,
)
from sensai.adapters.tui.commands.registry import CommandRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence


def default_registry(
    *,
    on_clear: Callable[[], Awaitable[None]] | None = None,
    persona_names: Callable[[], Sequence[str]] = tuple,
) -> CommandRegistry:
    """Build a registry holding every built-in command.

    Args:
        on_clear: Awaited by /clear before the engine history is cleared.
        persona_names: The personas /persona completes, asked on every
            completion; none by default.

    Returns:
        The registry, in the order the commands are listed in the menu.
    """
    registry = CommandRegistry()
    clear.register_self(registry, on_clear=on_clear)
    effort.register_self(registry)
    persona.register_self(registry, names=persona_names)
    mcp.register_self(registry)
    tools.register_self(registry)
    exit_.register_self(registry)
    return registry
