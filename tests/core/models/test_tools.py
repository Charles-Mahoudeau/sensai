"""Tests for the tool models."""

from __future__ import annotations

from pathlib import Path

from sensai.core.models import Attachment, ToolOutput


def test_images_are_recognized_by_their_media_type() -> None:
    """Only `image/*` attachments can be shown as pictures."""
    assert Attachment(Path("plot.png"), "image/png").is_image
    assert Attachment(Path("plot.svg"), "image/svg+xml").is_image
    assert not Attachment(Path("data.csv"), "text/csv").is_image


def test_tool_output_defaults_to_a_plain_success() -> None:
    """Without files or an error, a ToolOutput is just successful text."""
    output = ToolOutput("done")

    assert (output.content, output.attachments, output.is_error) == ("done", (), False)
