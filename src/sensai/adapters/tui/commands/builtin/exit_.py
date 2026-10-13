"""The /exit command: close the app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(registry: CommandRegistry) -> None:
    """Register /exit, and its /quit alias, into a command registry."""
    registry.register(CommandSpec("/exit", "Exit the app", aliases=("/quit",)), _exit)


async def _exit(context: CommandContext, argument: str) -> None:
    del argument
    context.exit()
