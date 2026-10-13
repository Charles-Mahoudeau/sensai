"""The completion menu shown above the prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.content import Content
from textual.widgets import OptionList

if TYPE_CHECKING:
    from sensai.adapters.tui.commands import Completion


class CommandMenu(OptionList):
    """The completions of the command being typed, shown above the prompt.

    It never takes the focus: the prompt drives it with the arrow keys, tab,
    enter and escape (see `PromptInput`).
    """

    can_focus = False

    DEFAULT_CSS = """
    CommandMenu {
        display: none;
        height: auto;
        max-height: 6;
    }
    """

    def __init__(self) -> None:
        """Start hidden, with no completions."""
        super().__init__(id="command-menu")
        self.completions: list[Completion] = []

    def show(self, completions: list[Completion]) -> None:
        """List `completions` with the first one highlighted; hide when empty."""
        self.completions = completions
        self.clear_options()
        width = max((len(item.label) for item in completions), default=0)
        self.add_options(
            Content.assemble(
                (item.label.ljust(width), "bold"), "   ", (item.description, "dim")
            )
            for item in completions
        )
        self.highlighted = 0 if completions else None
        self.display = bool(completions)

    def move(self, step: int) -> None:
        """Move the highlight by `step` rows, wrapping around the ends."""
        if self.completions:
            current = self.highlighted or 0
            self.highlighted = (current + step) % len(self.completions)

    @property
    def selected(self) -> Completion | None:
        """The highlighted completion, or None if the menu is hidden."""
        if not self.display or self.highlighted is None:
            return None
        return self.completions[self.highlighted]
