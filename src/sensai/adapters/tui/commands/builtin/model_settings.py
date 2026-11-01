"""The /model-settings command: show or set the generation options."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import Argument, CommandSpec

if TYPE_CHECKING:
    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry
    from sensai.core.models.llm import ChatOptions

# The settable options, the type their value is read as, and what they do.
SETTINGS: dict[str, tuple[type[float] | type[int], str]] = {
    "temperature": (float, "Randomness: 0 always picks the likeliest token"),
    "top_p": (float, "Sample only from the likeliest tokens totalling p"),
    "top_k": (int, "Sample only from the k likeliest tokens"),
    "seed": (int, "Same seed and settings give the same answer"),
    "num_ctx": (int, "Context length, in tokens"),
}
USAGE = "Use /model-settings <name> <value|default>, name one of: " + ", ".join(
    SETTINGS
)


def register_self(registry: CommandRegistry) -> None:
    """Register /model-settings into a command registry."""
    registry.register(
        CommandSpec(
            "/model-settings",
            "Show or set temperature, top_p, top_k, seed, num_ctx",
            arguments=tuple(
                Argument(name, help_) for name, (_, help_) in SETTINGS.items()
            ),
        ),
        _model_settings,
    )


async def _model_settings(context: CommandContext, argument: str) -> None:
    engine = context.engine
    if argument:
        name, _, raw = argument.partition(" ")
        raw = raw.strip()
        if name not in SETTINGS or not raw:
            await context.show_hint(USAGE)
            return
        kind = SETTINGS[name][0]
        try:
            value = None if raw == "default" else kind(raw)
            engine.chat_options = replace(engine.chat_options, **{name: value})
        except ValueError as error:
            await context.show_hint(f"Invalid {name} {raw!r}: {error}")
            return
    await context.show_hint(describe(engine.chat_options))


def describe(options: ChatOptions) -> str:
    """One line with every setting, `default` for those left to the model."""
    values = (
        f"{name} {'default' if (value := getattr(options, name)) is None else value}"
        for name in SETTINGS
    )
    return "Model settings: " + " · ".join(values)
