"""The /mcp command: list the MCP servers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.adapters.tui.panels import McpPanel

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(registry: CommandRegistry) -> None:
    """Register /mcp into a command registry."""
    registry.register(CommandSpec("/mcp", "List MCP servers"), _mcp)


async def _mcp(context: CommandContext, argument: str) -> None:
    del argument
    await context.open_panel(McpPanel(context.engine.mcp_servers()))
