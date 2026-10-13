"""The /tools command: list the tools and enable or disable them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.adapters.tui.panels import ToolsPanel

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(registry: CommandRegistry) -> None:
    """Register /tools into a command registry."""
    registry.register(CommandSpec("/tools", "Enable or disable tools"), _tools)


async def _tools(context: CommandContext, argument: str) -> None:
    del argument
    await context.open_panel(ToolsPanel(context.engine))
