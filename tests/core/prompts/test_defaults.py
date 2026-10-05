"""Tests for the default prompts shipped with the code."""

from __future__ import annotations

from sensai.core.prompts import JUDGE, SYSTEM, load_defaults


def test_system_and_judge_defaults_are_shipped() -> None:
    """Both defaults load, keyed by file name, with non-empty text."""
    defaults = load_defaults()

    assert {SYSTEM, JUDGE} <= defaults.keys()
    assert all(text.strip() for text in defaults.values())


def test_judge_default_asks_for_the_json_verdict() -> None:
    """The judge prompt describes the verdict format the comparison parses."""
    assert '"winner"' in load_defaults()[JUDGE]
