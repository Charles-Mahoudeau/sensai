"""The /usage command: show the session's tokens, context and model memory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.adapters.tui.panels import UsagePanel

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(registry: CommandRegistry) -> None:
    """Register /usage into a command registry."""
    registry.register(
        CommandSpec("/usage", "Show token, context and memory use"), _usage
    )


async def _usage(context: CommandContext, argument: str) -> None:
    del argument
    await context.open_panel(UsagePanel(await context.engine.usage_report()))
