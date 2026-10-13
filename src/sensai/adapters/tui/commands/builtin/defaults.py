"""The registry holding every built-in slash command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.builtin import clear, effort, exit_
from sensai.adapters.tui.commands.registry import CommandRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def default_registry(
    *, on_clear: Callable[[], Awaitable[None]] | None = None
) -> CommandRegistry:
    """Build a registry holding every built-in command.

    Args:
        on_clear: Awaited by /clear before the engine history is cleared.

    Returns:
        The registry, in the order the commands are listed in the menu.
    """
    registry = CommandRegistry()
    clear.register_self(registry, on_clear=on_clear)
    effort.register_self(registry)
    exit_.register_self(registry)
    return registry
