"""Registry and dispatch logic for slash commands typed in the prompt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from rich.highlighter import Highlighter
from rich.style import Style

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from rich.text import Text

    from sensai.adapters.tui.panels import Panel
    from sensai.core.engine import Engine


@dataclass(frozen=True, slots=True)
class Argument:
    """A value a command accepts, offered as a completion."""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Describe a slash command.

    Attributes:
        name: What the user types, slash included (`/clear`).
        description: One line shown next to the name in the completion menu.
        arguments: The values completed after the name; empty if it takes none.
        aliases: Other names that run the command, never offered as completions.
    """

    name: str
    description: str
    arguments: tuple[Argument, ...] = ()
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the name and the aliases."""
        for name in (self.name, *self.aliases):
            if not _is_command_name(name):
                raise ValueError(f"Command name {name!r} must be '/' and a word")


@dataclass(frozen=True, slots=True)
class Completion:
    """One entry of the completion menu.

    Attributes:
        value: The whole prompt text once the entry is accepted.
        label: The completed word, shown in the menu.
        description: The hint shown next to the label.
    """

    value: str
    label: str
    description: str


class CommandContext(Protocol):
    """What a command handler may do to the front-end running it."""

    @property
    def engine(self) -> Engine:
        """The engine the front-end drives."""
        ...

    async def show_hint(self, text: str) -> None:
        """Show a short message to the user."""
        ...

    async def clear_transcript(self) -> None:
        """Remove every message shown so far."""
        ...

    def refresh_status(self) -> None:
        """Show the engine's current state (such as its effort) again."""
        ...

    async def open_panel(self, panel: Panel) -> None:
        """Show a panel in place of the prompt until it is closed."""
        ...

    def exit(self) -> None:
        """Close the front-end."""
        ...


type CommandHandler = Callable[[CommandContext, str], Awaitable[None]]


class CommandRegistry:
    """Register commands, complete them while typed and dispatch them."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._commands: dict[str, tuple[CommandSpec, CommandHandler]] = {}
        self._names: dict[str, str] = {}  # name or alias -> command name

    def register(self, spec: CommandSpec, handler: CommandHandler) -> None:
        """Register a command handler under the spec's name and aliases.

        Raises:
            ValueError: The name or an alias is already taken.
        """
        for name in (spec.name, *spec.aliases):
            if name in self._names:
                raise ValueError(f"Command {name} is already registered")
        self._commands[spec.name] = (spec, handler)
        for name in (spec.name, *spec.aliases):
            self._names[name] = spec.name

    def specs(self) -> tuple[CommandSpec, ...]:
        """Return the registered command specifications, in registration order."""
        return tuple(spec for spec, _ in self._commands.values())

    def find(self, name: str) -> CommandSpec | None:
        """Return the command called `name` (or aliased to it), if any."""
        command = self._names.get(name)
        return self._commands[command][0] if command is not None else None

    def complete(self, text: str) -> list[Completion]:
        """Return the completions for the text typed so far.

        A partial command name completes to the matching commands; after a
        command and a space, the partial argument completes to its arguments.

        Args:
            text: The prompt text, unstripped.

        Returns:
            The matching completions, in registration order; empty if none.
        """
        if not text.startswith("/"):
            return []
        name, space, argument = text.partition(" ")
        if not space:
            return [
                Completion(
                    f"{spec.name} " if spec.arguments else spec.name,
                    spec.name,
                    spec.description,
                )
                for spec in self.specs()
                if spec.name.startswith(name)
            ]
        spec = self.find(name)
        prefix = argument.lstrip().lower()
        if spec is None or " " in prefix:
            return []
        return [
            Completion(f"{spec.name} {arg.name}", arg.name, arg.description)
            for arg in spec.arguments
            if arg.name.startswith(prefix)
        ]

    async def run(self, text: str, context: CommandContext) -> bool:
        """Run the command typed in `text`, if it is one.

        An unknown command is reported through `context.show_hint`.

        Args:
            text: The stripped prompt text.
            context: The front-end the handler acts on.

        Returns:
            False if the text is not a command (no leading slash), True otherwise.
        """
        if not text.startswith("/"):
            return False
        name, _, argument = text.partition(" ")
        command = self._names.get(name)
        if command is None:
            await context.show_hint(f"Unknown command {name}")
            return True
        _, handler = self._commands[command]
        await handler(context, argument.strip())
        return True


class CommandHighlighter(Highlighter):
    """Style the command name at the start of the prompt, if it is a known one."""

    def __init__(self, commands: CommandRegistry, style: Style | None = None) -> None:
        """Highlight the commands of `commands`, bold until a theme color is set."""
        self._commands = commands
        self.style = style or Style(bold=True)

    def highlight(self, text: Text) -> None:
        """Apply the style to a leading known command name."""
        name = text.plain.partition(" ")[0]
        if self._commands.find(name) is not None:
            text.stylize(self.style, 0, len(name))


def _is_command_name(name: str) -> bool:
    return len(name) > 1 and name.startswith("/") and not any(c.isspace() for c in name)
