"""The transcript line of a usage hint."""

from __future__ import annotations

from textual.widgets import Static


class HintMessage(Static):
    """A short, dim hint about how to use the prompt."""

    DEFAULT_CSS = """
    HintMessage {
        color: $text-disabled;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, text: str) -> None:
        """Render the hint text."""
        super().__init__(text, markup=False)
        self.text = text
