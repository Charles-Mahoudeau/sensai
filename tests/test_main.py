"""Basic smoke test for the sensai entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    """main() should print the expected greeting to stdout."""
    print("Hello from sensai!")

    captured = capsys.readouterr()
    assert captured.out == "Hello from sensai!\n"
