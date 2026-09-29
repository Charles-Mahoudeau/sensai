"""Tests for the Textual chat front-end, driven with a scripted engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.widgets import Input

from sensai.adapters.tui import SensaiApp
from sensai.adapters.tui.chat_app import EMPTY_INPUT_HINT
from sensai.adapters.tui.widgets import (
    AssistantMessage,
    ErrorMessage,
    HintMessage,
    UserMessage,
)
from sensai.core.agent import Agent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import ChatDone, TextDelta
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import LLMUnavailableError
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

    from textual.pilot import Pilot

    from sensai.core.models import ChatEvent, Message, ToolSpec
    from sensai.core.models.llm import ChatOptions
    from sensai.core.ports import LLM
    from tests.fakes.llm import Turn


class BlockingLLM:
    """Start an answer, then wait until the test releases it."""

    def __init__(self) -> None:
        """Create the release switch."""
        self.release = asyncio.Event()

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        options: ChatOptions | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Stream one fragment, then block until released."""
        del messages, tools, options
        yield TextDelta("Thinking")
        await self.release.wait()
        yield ChatDone()


def _app(llm: LLM) -> SensaiApp:
    engine = Engine(Agent(llm), Pipeline(), EventBus())
    return SensaiApp(engine, model="test-model")


def _run(app: SensaiApp, scenario: Callable[[Pilot[None]], Awaitable[None]]) -> None:
    async def run() -> None:
        async with app.run_test() as pilot:
            await scenario(pilot)

    asyncio.run(run())


async def _send(pilot: Pilot[None], text: str) -> None:
    pilot.app.query_one("#prompt", Input).value = text
    await pilot.press("enter")


async def _wait_until_idle(pilot: Pilot[None]) -> None:
    prompt = pilot.app.query_one("#prompt", Input)
    for _ in range(100):
        await pilot.pause()
        if not prompt.disabled:
            return
    raise AssertionError("the submission never finished")


type Transcript = UserMessage | AssistantMessage | ErrorMessage | HintMessage


def _texts[W: Transcript](app: SensaiApp, widget_type: type[W]) -> list[str]:
    return [widget.text for widget in app.query(widget_type)]


def test_streamed_answer_is_rendered() -> None:
    """Streamed fragments end up as one assistant message."""
    turns: list[Turn] = [[TextDelta("Bon"), TextDelta("jour")]]
    app = _app(FakeLLM(turns))

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        assert _texts(app, UserMessage) == ["Hello"]
        assert _texts(app, AssistantMessage) == ["Bonjour"]

    _run(app, scenario)


def test_empty_input_shows_a_hint_and_sends_nothing() -> None:
    """Blank input is never submitted to the model."""
    llm = FakeLLM([])
    app = _app(llm)

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "   ")
        await pilot.pause()

        assert _texts(app, HintMessage) == [EMPTY_INPUT_HINT]
        assert llm.messages == []

    _run(app, scenario)


def test_error_is_shown_and_the_session_continues() -> None:
    """An engine error is displayed, and the next message still works."""
    turns: list[Turn] = [[LLMUnavailableError("Ollama is down")], [TextDelta("Back")]]
    app = _app(FakeLLM(turns))

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        assert _texts(app, ErrorMessage) == ["Ollama is down"]
        assert _texts(app, AssistantMessage) == []

        await _send(pilot, "Again")
        await _wait_until_idle(pilot)

        assert _texts(app, AssistantMessage) == ["Back"]

    _run(app, scenario)


def test_exit_command_quits() -> None:
    """Typing /exit closes the app."""
    app = _app(FakeLLM([]))

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/exit")
        await pilot.pause()

        assert not app.is_running

    _run(app, scenario)


def test_prompt_is_disabled_while_generating() -> None:
    """A second message can't be sent until the answer is complete."""
    llm = BlockingLLM()
    app = _app(llm)

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await pilot.pause()

        assert app.query_one("#prompt", Input).disabled

        llm.release.set()
        await _wait_until_idle(pilot)

        assert _texts(app, AssistantMessage) == ["Thinking"]

    _run(app, scenario)


def test_escape_interrupts_the_answer() -> None:
    """Esc stops generation, keeps the partial answer and frees the prompt."""
    app = _app(BlockingLLM())

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await pilot.pause()

        await pilot.press("escape")
        await _wait_until_idle(pilot)

        assert _texts(app, AssistantMessage) == ["Thinking"]
        assert _texts(app, HintMessage) == ["(interrupted)"]

    _run(app, scenario)
