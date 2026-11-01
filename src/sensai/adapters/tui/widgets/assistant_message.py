"""The transcript entry of a model answer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Markdown

from sensai.adapters.tui.widgets.math_markdown import MathMarkdown

if TYPE_CHECKING:
    from textual.widgets.markdown import MarkdownStream


class AssistantMessage(MathMarkdown):
    """A model answer, rendered as Markdown (math included) while it streams in."""

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
