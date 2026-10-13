"""The transcript line of a message typed by the user."""

from __future__ import annotations

from textual.widgets import Static


class UserMessage(Static):
    """A message typed by the user."""

    DEFAULT_CSS = """
    UserMessage {
        color: $text-muted;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, text: str) -> None:
        """Render the user's text after a prompt marker."""
        super().__init__(f"> {text}", markup=False)
        self.text = text
