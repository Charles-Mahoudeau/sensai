"""The /mode command: show or set how the agent answers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import Argument, CommandSpec
from sensai.core.errors import ModeUnavailableError, SubmissionInProgressError

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry
    from sensai.core.agent.re_act import AgentMode

# The name each mode goes by in the chat, and the agent mode it selects.
MODES: dict[str, AgentMode] = {"default": "answer", "plan": "plan"}


def register_self(registry: CommandRegistry) -> None:
    """Register /mode into a command registry."""
    registry.register(
        CommandSpec(
            "/mode",
            "Answer fully, or only plan the method",
            arguments=(
                Argument("default", "Explain and solve"),
                Argument("plan", "Only the steps to follow, no answer"),
            ),
        ),
        _mode,
    )


async def _mode(context: CommandContext, argument: str) -> None:
    engine = context.engine
    if argument:
        wanted = MODES.get(argument.lower())
        if wanted is None:
            await context.show_hint(
                f"Unknown mode {argument!r}. Use one of: {', '.join(MODES)}"
            )
            return
        try:
            engine.set_mode(wanted)
        except (ModeUnavailableError, SubmissionInProgressError) as error:
            await context.show_hint(f"Could not change the mode: {error}")
            return
        context.refresh_status()
        await context.show_hint(f"Mode: {_name(engine.mode)}")
        return
    await context.show_hint(
        f"Mode: {_name(engine.mode)} (available: {', '.join(MODES)})"
    )


def _name(mode: AgentMode) -> str:
    """The chat name of an agent mode."""
    return next(name for name, value in MODES.items() if value == mode)
