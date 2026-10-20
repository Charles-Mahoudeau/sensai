"""The /persona command: show or switch the persona the agent acts as."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import Argument, CommandSpec
from sensai.core.errors import SubmissionInProgressError
from sensai.core.ports import PersonaError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry


def register_self(
    registry: CommandRegistry, *, names: Callable[[], Sequence[str]]
) -> None:
    """Register /persona into a command registry.

    Args:
        registry: Where the command is registered.
        names: The personas offered as completions, asked on every completion.
    """
    registry.register(
        CommandSpec(
            "/persona",
            "Switch persona",
            arguments=lambda: tuple(Argument(name, "") for name in names()),
        ),
        _persona,
    )


async def _persona(context: CommandContext, argument: str) -> None:
    engine = context.engine
    if argument:
        try:
            # reads the file again, so switching to the same name reloads it
            engine.set_persona(argument)
        except (PersonaError, SubmissionInProgressError) as error:
            await context.show_hint(str(error))
            return
        context.refresh_status()
    active = engine.persona.name if engine.persona is not None else "none"
    available = ", ".join(engine.persona_names()) or "none"
    await context.show_hint(f"Persona: {active} (available: {available})")
