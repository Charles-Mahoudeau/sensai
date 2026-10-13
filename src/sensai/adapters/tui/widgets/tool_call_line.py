"""The transcript line of one tool call."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.content import Content
from textual.widgets import Static

from sensai.adapters.tui.widgets._text import trim

if TYPE_CHECKING:
    from typing import Literal


class ToolCallLine(Static):
    """One tool call: "Calling tool …" while it runs, then its trimmed result."""

    DEFAULT_CSS = """
    ToolCallLine {
        color: $text-muted;
    }
    """

    RESULT_LIMIT = 80

    def __init__(self, name: str) -> None:
        """Start in the running state."""
        super().__init__(_running(name))
        self.tool_name = name
        self.text = f"● Calling tool {name}..."
        self.state: Literal["running", "done", "failed", "interrupted"] = "running"

    def finish(self, content: str, *, is_error: bool = False) -> None:
        """Replace the running line by the trimmed result of the call."""
        summary = trim(content, self.RESULT_LIMIT)
        if is_error:
            self.state = "failed"
            self.text = f"● Failed to call tool {self.tool_name}: {summary}"
            self.update(
                Content.assemble(
                    ("● Failed to call tool ", "$error"),
                    (self.tool_name, "$accent"),
                    (f": {summary}", "$error"),
                )
            )
        else:
            self.state = "done"
            self.text = f"● Called tool {self.tool_name}: {summary}"
            self.update(
                Content.assemble(
                    ("●", "$success"),
                    " Called tool ",
                    (self.tool_name, "$accent"),
                    f": {summary}",
                )
            )

    def interrupt(self) -> None:
        """Mark a call that never reported a result, e.g. after an interrupt."""
        self.state = "interrupted"
        self.text = f"● Interrupted tool {self.tool_name}…"
        self.update(
            Content.assemble("● Interrupted tool ", (self.tool_name, "$accent"), "…")
        )


def _running(name: str) -> Content:
    return Content.assemble("● Calling tool ", (name, "$accent"), "...")
