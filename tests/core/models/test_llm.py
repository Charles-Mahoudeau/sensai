"""Tests for the chat models."""

from __future__ import annotations

from datetime import timedelta

import pytest

from sensai.core.models.llm import ChatDone, Timings, Usage


def _timings(prompt_eval: timedelta, eval_: timedelta) -> Timings:
    return Timings(
        total=prompt_eval + eval_,
        load=timedelta(0),
        prompt_eval=prompt_eval,
        eval=eval_,
    )


def test_negative_duration_is_rejected() -> None:
    """A timing cannot go backwards."""
    with pytest.raises(ValueError, match=r"^eval must be non-negative"):
        Timings(
            total=timedelta(0),
            load=timedelta(0),
            prompt_eval=timedelta(0),
            eval=timedelta(seconds=-1),
        )


def test_speeds_are_tokens_per_second() -> None:
    """Each speed divides its token count by the matching phase duration."""
    done = ChatDone(
        Usage(completion_tokens=50, prompt_tokens=400),
        "stop",
        _timings(timedelta(milliseconds=500), timedelta(seconds=2)),
    )

    assert done.prompt_tokens_per_second == 800
    assert done.completion_tokens_per_second == 25


def test_speeds_are_unknown_without_timings() -> None:
    """A provider that reports no durations gives no speed."""
    done = ChatDone(Usage(completion_tokens=50, prompt_tokens=400))

    assert done.prompt_tokens_per_second is None
    assert done.completion_tokens_per_second is None


def test_speed_is_unknown_for_a_zero_duration() -> None:
    """A phase that took no measurable time gives no speed instead of failing."""
    done = ChatDone(
        Usage(completion_tokens=0, prompt_tokens=400),
        timings=_timings(timedelta(seconds=1), timedelta(0)),
    )

    assert done.completion_tokens_per_second is None
