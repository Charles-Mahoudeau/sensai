"""Public facade front-ends use to submit messages and subscribe to events."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Protocol

from sensai.core import agent
from sensai.core.agent.events import TurnCompleted
from sensai.core.errors import EngineError, SensaiError, SubmissionInProgressError
from sensai.core.events import (
    Done,
    ErrorEvent,
    Event,
    EventBus,
    MessageCompleted,
    MessageStarted,
    ThinkingGenerated,
    TokenGenerated,
)
from sensai.core.events.types import ToolRunFinished, ToolRunStarted
from sensai.core.models import Message, TextDelta
from sensai.core.models.llm import ThinkingDelta
from sensai.core.pipeline.base import Pipeline, ShortCircuit

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Sequence

    from sensai.core.agent.events import AgentEvent


class Runner(Protocol):
    """Protocol for a message processing runner."""

    def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Run the message processing pipeline for the given message."""
        ...


class Engine:
    """Coordinate the pipeline, runner and public event bus."""

    def __init__(
        self,
        runner: Runner,
        pipeline: Pipeline,
        bus: EventBus,
        *,
        system_prompt: str = "",
        history: Sequence[Message] = (),
    ) -> None:
        """Initialize the engine with its processing dependencies."""
        self._runner = runner
        self._pipeline = pipeline
        self._bus = bus
        self._system_prompt = system_prompt
        self._history: list[Message] = list(history)
        self._tasks: dict[str, asyncio.Task[None]] = {}

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

    async def _run(self, submission_id: str) -> None:
        try:
            await self._bus.publish(MessageStarted(submission_id))  # start

            messages = tuple(self._history)
            if self._system_prompt:
                messages = (Message.system(self._system_prompt), *messages)
            result = self._pipeline.run(messages)  # pipeline

            if isinstance(result, ShortCircuit):  # already has a reply
                self._history.append(result.reply)
                await self._bus.publish(MessageCompleted(submission_id, result.reply))

            else:  # requires asking the model
                replies = await self._stream_reply(submission_id, result.messages)
                if not replies:
                    raise SensaiError("no replies received from the model")
                self._history.extend(replies)
                await self._bus.publish(MessageCompleted(submission_id, replies[-1]))
        except SensaiError as error:
            await self._bus.publish(ErrorEvent(submission_id, error))
        except Exception as error:
            await self._bus.publish(ErrorEvent(submission_id, EngineError(str(error))))
        finally:
            self._tasks.pop(submission_id, None)
            await self._bus.publish(Done(submission_id))  # end

    async def _stream_reply(
        self, submission_id: str, messages: tuple[Message, ...]
    ) -> list[Message]:
        async for event in self._runner.run(messages):
            match event:
                case TextDelta(text):
                    await self._bus.publish(TokenGenerated(submission_id, text))
                case ThinkingDelta(text, ready):
                    await self._bus.publish(
                        ThinkingGenerated(submission_id, text, ready)
                    )
                case agent.events.ToolRunStarted(call):
                    await self._bus.publish(ToolRunStarted(submission_id, call))
                case agent.events.ToolRunFinished(call, result):
                    await self._bus.publish(
                        ToolRunFinished(submission_id, call, result)
                    )
                case TurnCompleted(messages=produced):
                    return produced
        raise RuntimeError("TurnCompleted event not received")

    @property
    def history(self) -> tuple[Message, ...]:
        """The conversation so far, oldest first."""
        return tuple(self._history)
