"""Tests for counting the token usage of a session."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sensai.core.models import Message, TextDelta
from sensai.core.models.llm import ChatDone, Timings, Usage, UsageTotals
from sensai.core.usage import MeteredLLM, UsageMeter
from tests.fakes import FakeLLM


def _done(prompt: int, completion: int, eval_seconds: float = 0) -> ChatDone:
    eval_ = timedelta(seconds=eval_seconds)
    return ChatDone(
        Usage(completion_tokens=completion, prompt_tokens=prompt),
        "stop",
        Timings(total=eval_, load=timedelta(0), prompt_eval=timedelta(0), eval=eval_),
    )


def test_metered_llm_forwards_events_and_counts_every_call() -> None:
    """Every call is counted, and the caller sees the stream unchanged."""
    turns = [[TextDelta("a"), _done(10, 2, 1)], [TextDelta("b"), _done(30, 4, 1)]]
    meter = UsageMeter()
    llm = MeteredLLM(FakeLLM(turns), meter)

    async def call() -> list[object]:
        return [event async for event in llm.chat([Message.user("hi")])]

    assert asyncio.run(call()) == turns[0]
    assert asyncio.run(call()) == turns[1]
    assert meter.total == UsageTotals(
        prompt_tokens=40,
        completion_tokens=6,
        calls=2,
        generation_time=timedelta(seconds=2),
    )
    assert meter.last == turns[1][1]


def test_total_starts_from_the_saved_usage() -> None:
    """A resumed session keeps counting from what was saved."""
    meter = UsageMeter(UsageTotals(prompt_tokens=100, calls=3))

    meter.record(_done(10, 1))

    assert meter.total == UsageTotals(prompt_tokens=110, completion_tokens=1, calls=4)


def test_take_unsaved_returns_only_what_is_new() -> None:
    """Taken usage is no longer unsaved, but still in the total."""
    meter = UsageMeter(UsageTotals(prompt_tokens=100, calls=3))
    meter.record(_done(10, 1))

    assert meter.take_unsaved() == UsageTotals(
        prompt_tokens=10, completion_tokens=1, calls=1
    )
    assert meter.take_unsaved() == UsageTotals()
    assert meter.total.calls == 4


def test_restored_usage_is_unsaved_again() -> None:
    """Usage that failed to save is taken again next time, with newer usage."""
    meter = UsageMeter()
    meter.record(_done(10, 1))
    taken = meter.take_unsaved()
    meter.record(_done(5, 1))

    meter.restore_unsaved(taken)

    assert meter.take_unsaved() == UsageTotals(
        prompt_tokens=15, completion_tokens=2, calls=2
    )


def test_reset_starts_a_new_session() -> None:
    """After a reset nothing is counted, saved or not."""
    meter = UsageMeter(UsageTotals(calls=3))
    meter.record(_done(10, 1))

    meter.reset()

    assert meter.total == UsageTotals()
    assert meter.take_unsaved() == UsageTotals()
    assert meter.last is None
