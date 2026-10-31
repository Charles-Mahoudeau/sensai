"""The transcript block of a file a tool produced, such as a plot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Static
from textual_image.widget import Image

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from sensai.core.models import Attachment


class ArtifactView(Vertical):
    """An image shown inline (when it is one), then the path of the saved file."""

    DEFAULT_CSS = """
    ArtifactView {
        height: auto;
        margin: 1 0 0 2;
    }
    ArtifactView > Image {
        width: auto;
        height: 20;
    }
    ArtifactView > .artifact-path {
        color: $text-muted;
    }
    """

    def __init__(self, attachment: Attachment) -> None:
        """Show `attachment`."""
        super().__init__()
        self.attachment = attachment

    def compose(self) -> ComposeResult:
        """An inline image for pictures, and the file path in every case."""
        if self.attachment.is_image:
            yield Image(self.attachment.path, on_error=_unreadable)
        yield Static(f"↳ {self.attachment.path}", markup=False, classes="artifact-path")


def _unreadable(error: Exception) -> Static:
    return Static(f"(cannot show the image: {error})", markup=False)
