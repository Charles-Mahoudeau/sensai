"""The /effort command: show or set the thinking effort."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import Argument, CommandSpec
from sensai.core.models import ThinkingEffort

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(registry: CommandRegistry) -> None:
    """Register /effort into a command registry."""
    registry.register(
        CommandSpec(
            "/effort",
            "Set thinking effort",
            arguments=tuple(
                Argument(effort.name.lower(), effort.label) for effort in ThinkingEffort
            ),
        ),
        _effort,
    )


async def _effort(context: CommandContext, argument: str) -> None:
    engine = context.engine
    if argument:
        try:
            wanted = ThinkingEffort[argument.upper()]
        except KeyError:
            levels = ", ".join(effort.name.lower() for effort in ThinkingEffort)
            await context.show_hint(
                f"Unknown effort {argument!r}. Use one of: {levels}"
            )
            return
        engine.thinking_effort = wanted
        context.refresh_status()
    # NONE if the runner can't reason, whatever was asked
    await context.show_hint(f"Thinking effort: {engine.thinking_effort.label}")
