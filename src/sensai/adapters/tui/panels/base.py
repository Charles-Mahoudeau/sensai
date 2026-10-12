"""The base of the panels shown in place of the prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message

if TYPE_CHECKING:
    from textual.binding import BindingType


class Panel(Vertical):
    """A panel shown in place of the prompt until escape closes it.

    The app mounts it, then removes it and gives the prompt back when it posts
    `Panel.Closed`.
    """

    can_focus = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
    ]

    class Closed(Message):
        """The panel asks to be closed."""

        def __init__(self, panel: Panel) -> None:
            """Name the panel to remove."""
            super().__init__()
            self.panel = panel

    def focus_first(self) -> None:
        """Focus the widget the keys should go to once the panel is shown."""
        self.focus()

    def action_close(self) -> None:
        """Ask the app to close the panel."""
        self.post_message(self.Closed(self))
