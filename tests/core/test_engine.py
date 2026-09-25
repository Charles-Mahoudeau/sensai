"""Tests for the public Engine facade."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sensai.core.engine import Engine
from sensai.core.events import (
    Done,
    EventBus,
    MessageCompleted,
    MessageStarted,
    TokenGenerated,
)
from sensai.core.models import ChatDone, Message, TextDelta
from sensai.core.pipeline.base import Pipeline

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.models import ChatEvent


class ScriptedRunner:
    """Stream a fixed answer for an Engine test."""

    def __init__(self, events: tuple[ChatEvent, ...]) -> None:
        """Store the events streamed by the runner."""
        self._events = events

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[ChatEvent]:
        """Yield the configured events in order."""
        del messages
        for event in self._events:
            yield event


class WaitingRunner:
    """Wait forever so the Engine can interrupt generation."""

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[ChatEvent]:
        """Wait until the surrounding task is cancelled."""
        del messages
        await asyncio.Event().wait()
        yield ChatDone()


def test_submit_streams_public_events() -> None:
    """A submitted message is translated into public Engine events."""

    async def run() -> None:
        bus = EventBus()
        engine = Engine(
            ScriptedRunner((TextDelta("Bon"), TextDelta("jour"), ChatDone())),
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
