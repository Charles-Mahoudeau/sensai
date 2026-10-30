"""Tests for the inline view of tool artifacts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from PIL import Image as Picture
from textual.app import App
from textual.widgets import Static
from textual_image.widget import Image

from sensai.adapters.tui.widgets import ArtifactView
from sensai.core.models import Attachment

if TYPE_CHECKING:
    from pathlib import Path

    from textual.app import ComposeResult


class _Host(App[None]):
    def __init__(self, attachment: Attachment) -> None:
        super().__init__()
        self.attachment = attachment

    def compose(self) -> ComposeResult:
        yield ArtifactView(self.attachment)


def _paths_and_images(attachment: Attachment) -> tuple[list[str], int]:
    async def run() -> tuple[list[str], int]:
        app = _Host(attachment)
        async with app.run_test() as pilot:
            await pilot.pause()
            paths = [
                str(w.content) for w in app.query(".artifact-path").results(Static)
            ]
            return paths, len(app.query(Image))

    return asyncio.run(run())


def test_an_image_is_shown_with_its_path(tmp_path: Path) -> None:
    """A picture gets an inline image, then the path of the saved file."""
    plot = tmp_path / "sine.png"
    Picture.new("RGB", (40, 20), "white").save(plot)

    paths, images = _paths_and_images(Attachment(plot, "image/png"))

    assert images == 1
    assert paths == [f"↳ {plot}"]


def test_other_files_show_only_their_path(tmp_path: Path) -> None:
    """A non-image file is listed by its path, without an image."""
    data = tmp_path / "data.csv"
    data.write_text("x,y")

    paths, images = _paths_and_images(Attachment(data, "text/csv"))

    assert images == 0
    assert paths == [f"↳ {data}"]
