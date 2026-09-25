"""Public facade front-ends use to submit messages and subscribe to events."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Protocol

from sensai.core.errors import EngineError, SensaiError, SubmissionInProgressError
from sensai.core.events import (
    Done,
    ErrorEvent,
    Event,
    EventBus,
    MessageCompleted,
    MessageStarted,
    TokenGenerated,
)
from sensai.core.models import ChatDone, Message, TextDelta
from sensai.core.pipeline.base import Pipeline, ShortCircuit

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from sensai.core.models import ChatEvent


class Runner(Protocol):
    """Protocol for a message processing runner."""

    def run(self, messages: tuple[Message, ...]) -> AsyncIterator[ChatEvent]:
        """Run the message processing pipeline for the given message."""
        ...


# plus tard il y aura une class comme elle par exemple agent
# cette classe aura dans elle les tools (les specs)
# et donc une fonction run


class Engine:
    """Coordinate the pipeline, runner and public event bus."""

    def __init__(self, runner: Runner, pipeline: Pipeline, bus: EventBus) -> None:
        """Initialize the engine with its processing dependencies."""
        self._runner = runner
        self._pipeline = pipeline
        self._bus = bus # delegue des abonnements et publication a un bus
        self._history: list[Message] = []
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # une entité s'inscris pour recevoir les événements
    def subscribe(self) -> AsyncGenerator[Event]:
        """Subscribe a front-end to the public event stream."""
        return self._bus.subscribe()

    # only for message write by an user like in a web
    # submit ->>> run ->>>> stream_reply
    def submit(self, text: str) -> str:
        """Submit a user message for processing."""
        if self._tasks:
            raise SubmissionInProgressError("A submission is already in progress.")
        submission_id = uuid.uuid4().hex
        self._history.append(Message.user(text))
        task = asyncio.create_task(self._run(submission_id))
        self._tasks[submission_id] = task
        return submission_id

    def interrupt(self, submission_id: str) -> None:
        """Interrupt a running submission."""
        task = self._tasks.get(submission_id)
        if task is not None:
            task.cancel()

    # Future features expose dedicated APIs when their scope requires them:
    # interrupt(), session management, persona/mode selection, etc.

    async def _run(self, submission_id: str) -> None:
        try:
            await self._bus.publish(MessageStarted(submission_id))  # ca commence

            result = self._pipeline.run(tuple(self._history))  # pipeline

            if isinstance(result, ShortCircuit):  # deja une réponse
                self._history.append(result.reply)
                await self._bus.publish(MessageCompleted(submission_id, result.reply))

            else:  # néccéssite de demander au model
                reply = await self._stream_reply(submission_id, result.messages)
                self._history.append(reply)
                await self._bus.publish(MessageCompleted(submission_id, reply))
        except SensaiError as error:
            await self._bus.publish(ErrorEvent(submission_id, error))
        except Exception as error:
            await self._bus.publish(ErrorEvent(submission_id, EngineError(str(error))))
        finally:
            self._tasks.pop(submission_id, None)
            await self._bus.publish(Done(submission_id))  # fin

    # discussion avec le model
    async def _stream_reply(
        self, submission_id: str, messages: tuple[Message, ...]
    ) -> Message:
        parts: list[str] = []
        async for event in self._runner.run(messages):
            match event:
                case TextDelta(text):
                    parts.append(text)
                    await self._bus.publish(TokenGenerated(submission_id, text))
                case ChatDone():
                    pass
        return Message.assistant("".join(parts))
