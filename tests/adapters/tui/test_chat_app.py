"""Tests for the Textual chat front-end, driven with a scripted engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.widgets import Input

from sensai.adapters.tui import SensaiApp
from sensai.adapters.tui.chat_app import EMPTY_INPUT_HINT
from sensai.adapters.tui.commands.builtin import default_registry
from sensai.adapters.tui.commands.builtin.clear import CLEARED_HINT
from sensai.adapters.tui.widgets import (
    AssistantMessage,
    CommandMenu,
    EffortLabel,
    ErrorMessage,
    HintMessage,
    ReasoningGroup,
    ThoughtStep,
    ToolCallLine,
    UserMessage,
)
from sensai.core.agent import Agent
from sensai.core.agent.events import ToolRunFinished, ToolRunStarted, TurnCompleted
from sensai.core.agent.re_act import ReActAgent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import (
    ChatDone,
    Message,
    TextDelta,
    ThinkingEffort,
    ToolCall,
    ToolResult,
)
from sensai.core.models.llm import ThinkingDelta
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import LLMUnavailableError
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

    from textual.pilot import Pilot

    from sensai.core.agent.events import AgentEvent
    from sensai.core.models import ChatEvent, ToolSpec
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
    engine = Engine(Agent(llm, ToolRegistry()), Pipeline(), EventBus())
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


def test_thinking_is_grouped_and_collapsed_when_the_answer_starts() -> None:
    """Reasoning fragments form one step in a group that folds under the answer."""
    turns: list[Turn] = [
        [ThinkingDelta("Let me "), ThinkingDelta("think"), TextDelta("42")]
    ]
    app = _app(FakeLLM(turns))

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        assert [step.text for step in app.query(ThoughtStep)] == ["Let me think"]
        assert _texts(app, AssistantMessage) == ["42"]
        group = app.query_one(ReasoningGroup)
        assert not group.live
        assert group.has_class("-collapsed")
        assert group.header_text.startswith("▸ Reasoned · 1 step")

    _run(app, scenario)


def test_reasoning_group_expands_with_click_and_ctrl_t() -> None:
    """The header toggles one group; ctrl+t toggles all of them."""
    turns: list[Turn] = [[ThinkingDelta("Hmm"), TextDelta("42")]]
    app = _app(FakeLLM(turns))

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)
        group = app.query_one(ReasoningGroup)

        await pilot.click(".reasoning-header")
        assert group.expanded
        assert group.has_class("-full")
        assert not group.has_class("-collapsed")
        assert group.header_text.startswith("▾ Reasoned")

        await pilot.press("ctrl+t")
        assert not group.expanded
        await pilot.press("ctrl+t")
        assert group.expanded

    _run(app, scenario)


def test_ready_thought_is_marked_in_its_title() -> None:
    """A closing `ready` delta tags the step as ready to answer."""
    app = _tool_app([ThinkingDelta("All known."), ThinkingDelta("", ready=True)])

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        step = app.query_one(ThoughtStep)
        assert step.ready
        assert step.title.endswith("ready to answer")

    _run(app, scenario)


def test_long_thought_shows_only_its_last_lines_while_streaming() -> None:
    """The live window is capped, then the step keeps the whole text."""
    step = ThoughtStep(1)
    step.add_fragment("word " * 400)

    assert step._tail().count("\n") + 1 == ThoughtStep.LIVE_LINES
    assert step._tail().startswith("…")
    assert len(step.text) == 2000


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


def test_quit_alias_quits() -> None:
    """/quit is kept as another name for /exit."""
    app = _app(FakeLLM([]))

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/quit")
        await pilot.pause()

        assert not app.is_running

    _run(app, scenario)


def test_clear_command_empties_the_transcript_and_history() -> None:
    """/clear runs the hook, then empties the screen and the engine history."""
    engine = Engine(
        Agent(FakeLLM([[TextDelta("Hi")]]), ToolRegistry()), Pipeline(), EventBus()
    )
    seen: list[int] = []

    async def on_clear() -> None:
        seen.append(len(engine.history))

    app = SensaiApp(
        engine, model="test-model", commands=default_registry(on_clear=on_clear)
    )

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        await _send(pilot, "/clear")
        await pilot.pause()

        assert seen == [2]
        assert engine.history == ()
        assert _texts(app, UserMessage) == []
        assert _texts(app, AssistantMessage) == []
        assert _texts(app, HintMessage) == [CLEARED_HINT]

    _run(app, scenario)


def test_effort_command_sets_and_shows_the_effort() -> None:
    """/effort <level> sets it, bare /effort shows it, a bad level is explained."""
    engine = Engine(ReActAgent(FakeLLM([]), ToolRegistry()), Pipeline(), EventBus())
    app = SensaiApp(engine, model="test-model")

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/effort high")
        await pilot.pause()
        await _send(pilot, "/effort")
        await pilot.pause()
        await _send(pilot, "/effort bogus")
        await pilot.pause()

        assert engine.thinking_effort is ThinkingEffort.HIGH
        assert app.query_one(EffortLabel).effort is ThinkingEffort.HIGH
        assert _texts(app, HintMessage) == [
            "Thinking effort: Deep thinking",
            "Thinking effort: Deep thinking",
            "Unknown effort 'bogus'. Use one of: none, low, medium, high, ultra",
        ]

    _run(app, scenario)


def test_unknown_command_is_not_sent() -> None:
    """An unknown command shows a hint and never reaches the model."""
    llm = FakeLLM([])
    app = _app(llm)

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/foo bar")
        await pilot.pause()

        assert _texts(app, HintMessage) == ["Unknown command /foo"]
        assert _texts(app, UserMessage) == []
        assert llm.messages == []

    _run(app, scenario)


def _menu_labels(app: SensaiApp) -> list[str]:
    menu = app.query_one(CommandMenu)
    return [item.label for item in menu.completions] if menu.display else []


def test_completion_menu_follows_the_typed_command() -> None:
    """The menu lists matches, tab completes, and arguments are offered next."""
    engine = Engine(ReActAgent(FakeLLM([]), ToolRegistry()), Pipeline(), EventBus())
    app = SensaiApp(engine, model="test-model")

    async def scenario(pilot: Pilot[None]) -> None:
        prompt = app.query_one("#prompt", Input)
        await pilot.press("/")
        assert _menu_labels(app) == ["/clear", "/effort", "/exit"]

        await pilot.press("e")
        assert _menu_labels(app) == ["/effort", "/exit"]

        await pilot.press("down", "up", "tab")
        assert prompt.value == "/effort "
        assert _menu_labels(app) == ["none", "low", "medium", "high", "ultra"]

        await pilot.press("h", "enter")
        await pilot.pause()
        assert engine.thinking_effort is ThinkingEffort.HIGH
        assert prompt.value == ""
        assert _menu_labels(app) == []
        assert _texts(app, HintMessage) == ["Thinking effort: Deep thinking"]

    _run(app, scenario)


def test_enter_on_a_partial_command_name_completes_it() -> None:
    """Enter accepts the highlight: /ex runs /exit, /eff waits for an argument."""
    app = _app(FakeLLM([]))

    async def scenario(pilot: Pilot[None]) -> None:
        await pilot.press("/", "e", "f", "f", "enter")
        assert app.query_one("#prompt", Input).value == "/effort "
        assert app.is_running

        app.query_one("#prompt", Input).value = ""
        await pilot.press("/", "e", "x", "enter")
        await pilot.pause()
        assert not app.is_running

    _run(app, scenario)


def test_escape_closes_the_menu_and_keys_fall_back_when_hidden() -> None:
    """Esc hides the menu; with it hidden, tab moves the focus as usual."""
    app = _app(FakeLLM([]))

    async def scenario(pilot: Pilot[None]) -> None:
        prompt = app.query_one("#prompt", Input)
        await pilot.press("/", "c")
        assert _menu_labels(app) == ["/clear"]

        await pilot.press("escape")
        assert _menu_labels(app) == []
        assert prompt.value == "/c"
        assert prompt.has_focus

        await pilot.press("tab")
        assert prompt.value == "/c"

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


class ScriptedRunner:
    """Replay fixed agent events, as a real agent run would emit them."""

    def __init__(self, events: list[AgentEvent]) -> None:
        """Keep the events to replay."""
        self._events = events

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Yield the scripted events."""
        del messages
        for event in self._events:
            yield event
        yield TurnCompleted([Message.assistant("done")])


def _tool_app(events: list[AgentEvent]) -> SensaiApp:
    engine = Engine(ScriptedRunner(events), Pipeline(), EventBus())
    return SensaiApp(engine, model="test-model")


def test_tool_calls_stack_above_the_answer() -> None:
    """Tool lines replace "Calling" by the trimmed result, answer comes last."""
    search = ToolCall("web_search", {"query": "x"}, id="1")
    fetch = ToolCall("fetch", {}, id="2")
    long_result = "line one\nline two " + "y" * 200
    app = _tool_app(
        [
            ToolRunStarted(search),
            ToolRunStarted(fetch),
            ToolRunFinished(search, ToolResult("web_search", long_result, "1")),
            ToolRunFinished(fetch, ToolResult.error("fetch", "boom", "2")),
            TextDelta("Answer"),
        ]
    )

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        lines = list(app.query(ToolCallLine))
        assert [(line.tool_name, line.state) for line in lines] == [
            ("web_search", "done"),
            ("fetch", "failed"),
        ]
        first = lines[0].text
        assert first.startswith("● Called tool web_search: line one line two y")
        assert first.endswith("…")
        assert "\n" not in first
        assert lines[1].text == "● Failed to call tool fetch: boom"

        order = [type(w) for w in app.query("#transcript > *")]
        assert order == [UserMessage, ReasoningGroup, AssistantMessage]

    _run(app, scenario)


def test_text_between_tool_calls_keeps_its_place() -> None:
    """A preamble before a tool call stays above that tool line."""
    call = ToolCall("web_search", id="1")
    app = _tool_app(
        [
            TextDelta("Let me search"),
            ToolRunStarted(call),
            ToolRunFinished(call, ToolResult("web_search", "ok", "1")),
            TextDelta("Found it"),
        ]
    )

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        order = [type(w) for w in app.query("#transcript > *")]
        assert order == [
            UserMessage,
            AssistantMessage,
            ReasoningGroup,
            AssistantMessage,
        ]
        assert _texts(app, AssistantMessage) == ["Let me search", "Found it"]

    _run(app, scenario)


def test_thoughts_and_tool_calls_share_one_group_per_turn() -> None:
    """Steps and tool lines nest in a single group, with a counted summary."""
    search = ToolCall("web_search", {"query": "x"}, id="1")
    app = _tool_app(
        [
            ThinkingDelta("Need the web."),
            ToolRunStarted(search),
            ToolRunFinished(search, ToolResult("web_search", "found", "1")),
            ThinkingDelta("Got it."),
            ThinkingDelta("", ready=True),
            TextDelta("Answer"),
        ]
    )

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "Hello")
        await _wait_until_idle(pilot)

        group = app.query_one(ReasoningGroup)
        assert [step.number for step in group.query(ThoughtStep)] == [1, 2]
        assert len(group.query(ToolCallLine)) == 1
        assert group.header_text.startswith("▸ Reasoned · 2 steps · 1 tool")
        assert len(app.query(ReasoningGroup)) == 1

    _run(app, scenario)


def test_ctrl_r_cycles_the_thinking_effort_shown_in_the_status_bar() -> None:
    """Ctrl+R advances the effort, wraps after Ultra and updates the label."""
    engine = Engine(ReActAgent(FakeLLM([]), ToolRegistry()), Pipeline(), EventBus())
    app = SensaiApp(engine, model="test-model")

    async def scenario(pilot: Pilot[None]) -> None:
        label = app.query_one(EffortLabel)
        assert label.effort is ThinkingEffort.MEDIUM

        await pilot.press("ctrl+r")
        assert label.effort is ThinkingEffort.HIGH
        await pilot.press("ctrl+r")
        assert label.effort is ThinkingEffort.ULTRA
        assert label._rainbow_timer is not None
        await pilot.press("ctrl+r")
        assert label.effort is ThinkingEffort.NONE
        assert label._rainbow_timer is None
        assert str(label.render()) == "No thinking"
        assert app._engine.thinking_effort is ThinkingEffort.NONE

    _run(app, scenario)
