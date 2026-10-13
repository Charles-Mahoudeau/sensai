"""The transcript line of an engine error."""

from __future__ import annotations

from textual.widgets import Static


class ErrorMessage(Static):
    """An error reported by the engine."""

    DEFAULT_CSS = """
    ErrorMessage {
        color: $error;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, text: str) -> None:
        """Render the error text."""
        super().__init__(f"✗ error: {text}", markup=False)
        self.text = text
