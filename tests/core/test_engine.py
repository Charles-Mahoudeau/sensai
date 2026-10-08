"""Tests for the public Engine facade."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sensai.core.agent.events import TurnCompleted
from sensai.core.agent.re_act import ReActAgent
from sensai.core.engine import Engine
from sensai.core.events import (
    Done,
    EventBus,
    MessageCompleted,
    MessageStarted,
    ThinkingGenerated,
    TokenGenerated,
)
from sensai.core.models import Message, TextDelta, ToolCall
from sensai.core.models.llm import ThinkingDelta, ToolCallRequest
from sensai.core.pipeline.base import Pipeline
from sensai.core.tools.builtin import web_search
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    import pytest

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


def test_model_receives_exactly_one_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engine adds the system message; the agent doesn't add another one."""

    async def search(args: Mapping[str, Any]) -> str:
        del args
        return "result"

    monkeypatch.setattr(web_search, "_web_search", search)
    llm = FakeLLM(
        [
            [TextDelta("I need data.")],
            [ToolCallRequest(ToolCall("web_search", {"query": "q"}, id="c1"))],
            [TextDelta("I am ready to answer.")],
            [TextDelta("Done.")],
        ]
    )

    async def run() -> None:
        registry = ToolRegistry()
        web_search.register_self(registry)
        engine = Engine(
            ReActAgent(llm, registry), Pipeline(), EventBus(), system_prompt="SYSTEM"
        )
        events = engine.subscribe()
        engine.submit("Hello")
        async for event in events:
            if isinstance(event, Done):
                break
        await events.aclose()

    asyncio.run(run())

    assert len(llm.messages) == 4
    for request in llm.messages:
        assert [m.content for m in request if m.role == "system"] == ["SYSTEM"]
        assert request[0].role == "system"
