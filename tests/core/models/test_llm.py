"""Tests for the chat models."""

from __future__ import annotations

from datetime import timedelta

import pytest

from sensai.core.models.llm import (
    ChatDone,
    LoadedModel,
    Timings,
    Usage,
    UsageReport,
    UsageTotals,
)


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


def test_ram_is_the_part_not_in_vram() -> None:
    """A model too big for the GPU spills the rest to system memory."""
    model = LoadedModel(name="m", size_bytes=10, vram_bytes=6)

    assert model.ram_bytes == 4
    assert not model.fully_on_gpu


def test_model_entirely_in_vram_uses_no_ram() -> None:
    """A model that fits on the GPU has nothing in system memory."""
    model = LoadedModel(name="m", size_bytes=10, vram_bytes=10)

    assert model.ram_bytes == 0
    assert model.fully_on_gpu


def test_negative_size_is_rejected() -> None:
    """A model cannot use a negative amount of memory."""
    with pytest.raises(ValueError, match="vram_bytes must be non-negative"):
        LoadedModel(name="m", size_bytes=10, vram_bytes=-1)


def test_usage_totals_add_one_response() -> None:
    """A response adds its tokens, one call, and its generation time."""
    done = ChatDone(
        Usage(completion_tokens=50, prompt_tokens=400),
        "stop",
        _timings(timedelta(milliseconds=500), timedelta(seconds=2)),
    )

    totals = UsageTotals(prompt_tokens=100, calls=1).add(done)

    assert totals == UsageTotals(
        prompt_tokens=500,
        completion_tokens=50,
        calls=2,
        generation_time=timedelta(seconds=2),
    )
    assert totals.total_tokens == 550
    assert totals.completion_tokens_per_second == 25


def test_usage_totals_without_timings_have_no_speed() -> None:
    """A response without durations is counted, with no generation time."""
    totals = UsageTotals().add(ChatDone(Usage(completion_tokens=5, prompt_tokens=1)))

    assert totals.calls == 1
    assert totals.generation_time == timedelta(0)
    assert totals.completion_tokens_per_second is None


def test_usage_totals_reject_negative_counts() -> None:
    """A total cannot go below zero."""
    with pytest.raises(ValueError, match="calls must be non-negative"):
        UsageTotals(calls=-1)


def test_context_ratio_is_the_used_part_of_the_window() -> None:
    """The ratio compares the latest call's tokens to the model's window."""
    model = LoadedModel(name="m", size_bytes=1, vram_bytes=1, context_length=1_000)

    report = UsageReport(loaded_model=model, context_used=250)

    assert report.context_limit == 1_000
    assert report.context_ratio == 0.25


def test_context_ratio_is_unknown_without_a_window() -> None:
    """No loaded model, no reported window or a zero window gives no ratio."""
    unknown = LoadedModel(name="m", size_bytes=1, vram_bytes=1)
    empty = LoadedModel(name="m", size_bytes=1, vram_bytes=1, context_length=0)

    assert UsageReport(context_used=250).context_ratio is None
    assert UsageReport(loaded_model=unknown, context_used=250).context_ratio is None
    assert UsageReport(loaded_model=empty, context_used=250).context_ratio is None
