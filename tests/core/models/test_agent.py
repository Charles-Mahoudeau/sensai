"""Tests for the agent models."""

from __future__ import annotations

from sensai.core.models import ThinkingEffort


def test_next_goes_from_lowest_to_highest_then_wraps() -> None:
    """Cycling visits every effort in order and loops back to the lowest."""
    effort = ThinkingEffort.NONE
    seen = [effort]
    for _ in range(len(ThinkingEffort)):
        effort = effort.next()
        seen.append(effort)

    assert seen == [*ThinkingEffort, ThinkingEffort.NONE]
