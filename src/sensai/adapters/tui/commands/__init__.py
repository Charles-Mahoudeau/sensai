"""Slash commands typed in the prompt: specs, handlers and their registry."""

from sensai.adapters.tui.commands.registry import (
    Argument,
    CommandContext,
    CommandHandler,
    CommandHighlighter,
    CommandRegistry,
    CommandSpec,
    Completion,
)

__all__ = [
    "Argument",
    "CommandContext",
    "CommandHandler",
    "CommandHighlighter",
    "CommandRegistry",
    "CommandSpec",
    "Completion",
]
