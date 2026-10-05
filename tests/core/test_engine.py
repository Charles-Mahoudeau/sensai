"""Tests for the public Engine facade."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sensai.core.agent.events import TurnCompleted
from sensai.core.engine import Engine
from sensai.core.events import (
    Done,
    EventBus,
    MessageCompleted,
    MessageStarted,
    ThinkingGenerated,
    TokenGenerated,
)
from sensai.core.models import Message, TextDelta, ThinkingEffort
from sensai.core.models.llm import ThinkingDelta
from sensai.core.pipeline.base import Pipeline

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.events import AgentEvent


class ScriptedRunner:
    """Stream a fixed answer for an Engine test."""

    def __init__(self, events: tuple[AgentEvent, ...]) -> None:
        """Store the events streamed by the runner."""
        self._events = events

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Yield the configured events in order."""
        del messages
        for event in self._events:
            yield event


class WaitingRunner:
    """Wait forever so the Engine can interrupt generation."""

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Wait until the surrounding task is cancelled."""
        del messages
        await asyncio.Event().wait()
        yield TurnCompleted([])


def test_submit_streams_public_events() -> None:
    """A submitted message is translated into public Engine events."""

    async def run() -> None:
        bus = EventBus()
        engine = Engine(
            ScriptedRunner(
                (
                    TextDelta("Bon"),
                    TextDelta("jour"),
                    TurnCompleted([Message.assistant("Bonjour")]),
                )
            ),
            Pipeline(),
            bus,
        )
        events = engine.subscribe()

        submission_id = engine.submit("Hello")

        assert await anext(events) == MessageStarted(submission_id)
        assert await anext(events) == TokenGenerated(submission_id, "Bon")
        assert await anext(events) == TokenGenerated(submission_id, "jour")
        assert await anext(events) == MessageCompleted(
            submission_id, Message.assistant("Bonjour")
        )
        assert await anext(events) == Done(submission_id)
        await events.aclose()

    asyncio.run(run())


def test_thinking_is_published_as_its_own_event() -> None:
    """Reasoning fragments are relayed apart from the answer tokens."""

    async def run() -> None:
        engine = Engine(
            ScriptedRunner(
                (
                    ThinkingDelta("Hmm"),
                    TextDelta("Hi"),
                    TurnCompleted([Message.assistant("Hi")]),
                )
            ),
            Pipeline(),
            EventBus(),
        )
        events = engine.subscribe()

        submission_id = engine.submit("Hello")

        assert await anext(events) == MessageStarted(submission_id)
        assert await anext(events) == ThinkingGenerated(submission_id, "Hmm")
        assert await anext(events) == TokenGenerated(submission_id, "Hi")
        await events.aclose()

    asyncio.run(run())


def test_interrupt_ends_a_running_submission() -> None:
    """Interrupting a submission closes its event stream with Done."""

    async def run() -> None:
        bus = EventBus()
        engine = Engine(WaitingRunner(), Pipeline(), bus)
        events = engine.subscribe()

        submission_id = engine.submit("Hello")
        assert await anext(events) == MessageStarted(submission_id)

        engine.interrupt(submission_id)

        assert await anext(events) == Done(submission_id)
        await events.aclose()

    asyncio.run(run())


class EffortRunner(ScriptedRunner):
    """A scripted runner exposing a settable thinking effort."""

    def __init__(self) -> None:
        """Start with no events and the default effort."""
        super().__init__(())
        self.thinking_effort = ThinkingEffort.NONE


def test_thinking_effort_cycles_and_reaches_the_runner() -> None:
    """Cycling the effort wraps after the highest and updates the runner."""
    runner = EffortRunner()
    runner.thinking_effort = ThinkingEffort.HIGH
    engine = Engine(runner, Pipeline(), EventBus())
    assert engine.thinking_effort is ThinkingEffort.HIGH

    assert engine.cycle_thinking_effort() is ThinkingEffort.ULTRA
    assert runner.thinking_effort is ThinkingEffort.ULTRA
    assert engine.cycle_thinking_effort() is ThinkingEffort.NONE
    assert runner.thinking_effort is ThinkingEffort.NONE


def test_thinking_effort_works_with_runners_that_do_not_support_it() -> None:
    """Without runner support the effort stays NONE and cycling is a no-op."""
    engine = Engine(ScriptedRunner(()), Pipeline(), EventBus())

    assert engine.cycle_thinking_effort() is ThinkingEffort.NONE
