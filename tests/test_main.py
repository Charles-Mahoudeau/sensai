"""Basic smoke test for the sensai entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai import main

if TYPE_CHECKING:
    import pytest


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    """main() should print the expected greeting to stdout."""
    main()

    captured = capsys.readouterr()
    assert captured.out == "Hello from sensai!\n"
