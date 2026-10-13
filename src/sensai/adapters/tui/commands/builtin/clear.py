"""The /clear command: forget the conversation and start a new session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry

CLEARED_HINT = "(conversation cleared)"


def register_self(
    registry: CommandRegistry,
    *,
    on_clear: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Register /clear into a command registry.

    Args:
        registry: The registry to add the command to.
        on_clear: Awaited before the engine history is cleared, for example to
            save the session and start a new one.
    """

    async def clear(context: CommandContext, argument: str) -> None:
        del argument
        if on_clear is not None:
            try:
                await on_clear()
            except SensaiError as error:
                await context.show_hint(f"(could not clear the conversation: {error})")
                return
        context.engine.clear()
        await context.clear_transcript()
        await context.show_hint(CLEARED_HINT)

    registry.register(
        CommandSpec("/clear", "Clear the conversation and start a new session"),
        clear,
    )
