"""The /sessions command: list the stored sessions by title."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.adapters.tui.panels import SessionsPanel
from sensai.core.ports import StorageError

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(registry: CommandRegistry) -> None:
    """Register /sessions, and its alias /chats, into a command registry."""
    registry.register(
        CommandSpec("/sessions", "List your sessions", aliases=("/chats",)),
        _sessions,
    )


async def _sessions(context: CommandContext, argument: str) -> None:
    del argument
    try:
        sessions = await context.engine.list_sessions()
    except StorageError as error:
        await context.show_hint(f"Could not read the sessions: {error}")
        return
    await context.open_panel(SessionsPanel(sessions))
