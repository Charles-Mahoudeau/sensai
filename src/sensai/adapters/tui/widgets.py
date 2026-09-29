"""Widgets rendering the chat transcript."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Markdown, Static

if TYPE_CHECKING:
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
