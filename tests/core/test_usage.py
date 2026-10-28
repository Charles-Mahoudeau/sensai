"""Tests for counting the token usage of a session."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from sensai.core.model_memory import ModelMemory
from sensai.core.models import Message, TextDelta
from sensai.core.models.llm import (
    ChatDone,
    LoadedModel,
    Timings,
    Usage,
    UsageReport,
    UsageTotals,
)
from sensai.core.ports import LLMUnavailableError, ModelNotFoundError
from sensai.core.usage import MeteredLLM, UsageMeter, usage_report
from tests.fakes import FakeLLM, FakeModelMonitor

if TYPE_CHECKING:
    from collections.abc import Sequence


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


def _report(
    meter: UsageMeter | None, monitor: FakeModelMonitor | None = None
) -> UsageReport:
    memory = ModelMemory(monitor, "qwen3:8b") if monitor is not None else None
    return asyncio.run(usage_report(meter, memory))


def test_report_gathers_usage_context_and_memory() -> None:
    """The context fill is the latest call's tokens, against the loaded window."""
    model = LoadedModel(
        name="qwen3:8b", size_bytes=10, vram_bytes=10, context_length=8_192
    )
    meter = UsageMeter(UsageTotals(prompt_tokens=100, calls=1))
    meter.record(_done(4_000, 96))

    report = _report(meter, FakeModelMonitor(model))

    assert report.session == meter.total
    assert report.loaded_model == model
    assert report.context_used == 4_096
    assert report.context_ratio == 0.5
    assert report.monitor_error is None


def test_report_without_meter_or_monitor_is_empty() -> None:
    """Nothing counted and no monitor gives an all-unknown report."""
    assert _report(None) == UsageReport()


def test_report_before_the_first_call_has_no_context() -> None:
    """Right after a restart the context fill is unknown."""
    report = _report(UsageMeter(UsageTotals(calls=3)))

    assert report.context_used is None
    assert report.context_ratio is None


def test_report_keeps_the_usage_when_the_monitor_fails() -> None:
    """An unreachable server only leaves the memory out, with the reason."""

    class _DownMonitor(FakeModelMonitor):
        async def loaded_models(self) -> Sequence[LoadedModel]:
            raise LLMUnavailableError("cannot reach Ollama")

    meter = UsageMeter()
    meter.record(_done(10, 1))

    report = _report(meter, _DownMonitor())

    assert report.session.calls == 1
    assert report.loaded_model is None
    assert report.monitor_error == "cannot reach Ollama"


def test_report_has_the_model_maximum_context() -> None:
    """The trained window is reported next to the loaded one."""
    model = LoadedModel(
        name="qwen3:8b", size_bytes=10, vram_bytes=10, context_length=4_096
    )

    report = _report(UsageMeter(), FakeModelMonitor(model, max_context=131_072))

    assert report.context_limit == 4_096
    assert report.context_max == 131_072


def test_report_without_the_maximum_keeps_the_rest() -> None:
    """A failed `/api/show` only leaves the maximum out."""

    class _NoShowMonitor(FakeModelMonitor):
        async def max_context_length(self, model: str) -> int | None:
            raise ModelNotFoundError(model)

    model = LoadedModel(name="qwen3:8b", size_bytes=10, vram_bytes=10)

    report = _report(UsageMeter(), _NoShowMonitor(model))

    assert report.loaded_model == model
    assert report.context_max is None
    assert report.monitor_error is None


def test_a_down_server_is_not_asked_for_the_maximum() -> None:
    """When `/api/ps` fails, `/api/show` is skipped: one timeout, not two."""

    class _DownMonitor(FakeModelMonitor):
        async def loaded_models(self) -> Sequence[LoadedModel]:
            raise LLMUnavailableError("cannot reach Ollama")

    monitor = _DownMonitor(max_context=131_072)

    report = _report(UsageMeter(), monitor)

    assert monitor.show_calls == 0
    assert report.context_max is None
