"""Widgets rendering the chat transcript."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.content import Content
from textual.widgets import Markdown, Static

if TYPE_CHECKING:
    from typing import Literal

    from textual.widgets.markdown import MarkdownStream


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


class AssistantMessage(Markdown):
    """A model answer, rendered as Markdown while it streams in."""

    DEFAULT_CSS = """
    AssistantMessage {
        margin: 1 0 0 0;
        padding: 0;
        background: transparent;
    }
    """

    def __init__(self) -> None:
        """Start with an empty document."""
        super().__init__()
        self.text = ""
        self._stream: MarkdownStream | None = None

    async def add_fragment(self, fragment: str) -> None:
        """Append a streamed fragment to the answer."""
        if self._stream is None:
            self._stream = Markdown.get_stream(self)
        self.text += fragment
        await self._stream.write(fragment)

    async def finish(self) -> None:
        """Flush the remaining fragments and stop streaming."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None


class ThinkingMessage(Static):
    """The model's reasoning: a "Thinking..." header, then the streamed text."""

    DEFAULT_CSS = """
    ThinkingMessage {
        color: $text-muted;
        margin: 1 0 0 0;
        text-style: italic;
    }
    """

    HEADER = "Thinking..."

    def __init__(self) -> None:
        """Start with the header and no reasoning yet."""
        super().__init__(self.HEADER, markup=False)
        self.text = ""

    def add_fragment(self, fragment: str) -> None:
        """Append a streamed fragment of reasoning."""
        self.text += fragment
        self.update(f"{self.HEADER}\n{self.text.lstrip()}")


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
        summary = _trim(content, self.RESULT_LIMIT)
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


def _trim(text: str, limit: int) -> str:
    """Collapse whitespace into a single line and cut it at ``limit`` characters."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


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
