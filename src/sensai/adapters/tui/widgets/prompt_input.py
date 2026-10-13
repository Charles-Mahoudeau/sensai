"""The prompt the user types in."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.style import Style
from textual.binding import Binding
from textual.widgets import Input

from sensai.adapters.tui.commands import CommandHighlighter
from sensai.adapters.tui.companion import Companion, Mood

if TYPE_CHECKING:
    from textual.binding import BindingType
    from textual.theme import Theme

    from sensai.adapters.tui.commands import CommandRegistry
    from sensai.adapters.tui.widgets.command_menu import CommandMenu


class PromptInput(Input):
    """The prompt: highlights known commands and drives the completion menu.

    While the menu is shown, up/down move its highlight, tab accepts it, enter
    accepts it (then submits, unless the command still needs an argument) and
    escape closes it. Otherwise these keys keep their usual meaning.

    The companion is drawn in its top border, and watches the user type.
    """

    COMPANION_INTERVAL = 0.2

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_completion(-1)", "Previous completion", show=False),
        Binding("down", "move_completion(1)", "Next completion", show=False),
        Binding("tab", "accept_completion", "Complete", show=False),
        Binding("escape", "close_completions", "Close completions", show=False),
    ]

    MENU_ACTIONS = frozenset(
        {"move_completion", "accept_completion", "close_completions"}
    )

    def __init__(
        self,
        menu: CommandMenu,
        commands: CommandRegistry,
        *,
        placeholder: str,
        id: str,
    ) -> None:
        """Create the prompt that completes `commands` into `menu`."""
        self._highlighter = CommandHighlighter(commands)
        super().__init__(placeholder=placeholder, highlighter=self._highlighter, id=id)
        self._menu = menu
        self._commands = commands
        self.companion = Companion()

    def on_mount(self) -> None:
        """Color commands with the theme accent, and animate the companion."""
        self._use_theme(self.app.current_theme)
        self.app.theme_changed_signal.subscribe(self, self._use_theme)
        self._tick_companion()
        self.set_interval(self.COMPANION_INTERVAL, self._tick_companion)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Enable the menu keys only while the menu is shown."""
        if action in self.MENU_ACTIONS:
            return self._menu.display
        return super().check_action(action, parameters)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Refresh the completions for the new text."""
        if event.input is self:
            self._menu.show(
                self._commands.complete(event.value) if not self.disabled else []
            )
            self.companion.poke()
            if not self.disabled:
                self.companion.set_mood(Mood.TYPING if event.value else Mood.IDLE)

    def action_move_completion(self, step: int) -> None:
        """Highlight another completion."""
        self._menu.move(step)

    def action_accept_completion(self) -> None:
        """Replace the text with the highlighted completion."""
        selected = self._menu.selected
        if selected is not None:
            self.value = selected.value
            self.cursor_position = len(self.value)

    def action_close_completions(self) -> None:
        """Hide the menu until the text changes."""
        self._menu.show([])

    async def action_submit(self) -> None:
        """Submit, accepting the highlighted completion first if there is one.

        A completion that still needs an argument (it ends with a space) is
        only accepted, so that its arguments can be picked next.
        """
        selected = self._menu.selected
        if selected is not None and self.value.strip() != selected.value.strip():
            self.action_accept_completion()
            if selected.value.endswith(" "):
                return
        await super().action_submit()

    def _tick_companion(self) -> None:
        frame = self.companion.frame()
        if frame != self.border_title:
            self.border_title = frame

    def _use_theme(self, theme: Theme) -> None:
        self._highlighter.style = Style(color=theme.accent, bold=True)
        self.refresh()
