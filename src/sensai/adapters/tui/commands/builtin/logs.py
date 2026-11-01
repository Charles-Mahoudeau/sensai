"""The /logs command: show this session's log records, live."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.adapters.tui.panels import LogsPanel

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry
    from sensai.adapters.tui.log_buffer import LogBuffer

NO_LOGS_HINT = "(logs are not collected in this session)"


def register_self(
    registry: CommandRegistry, *, buffer: LogBuffer | None = None
) -> None:
    """Register /logs into a command registry.

    Args:
        registry: The registry to add the command to.
        buffer: Where the records come from; without it, /logs only says so.
    """

    async def logs(context: CommandContext, argument: str) -> None:
        del argument
        if buffer is None:
            await context.show_hint(NO_LOGS_HINT)
            return
        await context.open_panel(LogsPanel(buffer))

    registry.register(CommandSpec("/logs", "Show the session's logs, live"), logs)
