"""Tests for the Textual chat front-end, driven with a scripted engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.widgets import Button, Input

from sensai.adapters.tui import SensaiApp
from sensai.adapters.tui.chat_app import EMPTY_INPUT_HINT
from sensai.adapters.tui.commands.builtin import default_registry
from sensai.adapters.tui.commands.builtin.clear import CLEARED_HINT
from sensai.adapters.tui.panels import McpPanel, Panel, ToolsPanel
from sensai.adapters.tui.panels.tools import ToolList
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
    McpServerStatus,
    Message,
    TextDelta,
    ThinkingEffort,
    ToolCall,
    ToolResult,
    ToolSpec,
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
    from sensai.core.models import ChatEvent
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
        assert _menu_labels(app) == ["/clear", "/effort", "/mcp", "/tools", "/exit"]

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


async def _noop(arguments: object) -> str:
    del arguments
    return ""


def _tools_app() -> tuple[SensaiApp, Engine]:
    registry = ToolRegistry()
    registry.register(ToolSpec("web_search", "Search the web"), _noop)
    for name in ("get_me", "delete_repository", "delete_file"):
        registry.register(
            ToolSpec(f"github__{name}", f"Do {name}"), _noop, source="github"
        )
    engine = Engine(
        Agent(FakeLLM([]), registry), Pipeline(), EventBus(), tools=registry
    )
    return SensaiApp(engine, model="test-model"), engine


def _title(app: SensaiApp) -> str:
    return str(app.query_one(ToolsPanel).border_title)


def _enabled(engine: Engine) -> list[str]:
    return [tool.spec.name for tool in engine.tools() if tool.enabled]


def test_tools_panel_replaces_the_prompt_and_escape_restores_it() -> None:
    """/tools hides the prompt, focuses the filter; escape gives the prompt back."""
    app, _ = _tools_app()

    async def scenario(pilot: Pilot[None]) -> None:
        prompt = app.query_one("#prompt", Input)
        await _send(pilot, "/tools")
        await pilot.pause()

        assert not prompt.display
        assert app.focused is app.query_one("#tools-filter", Input)
        assert _title(app) == "Tools · 4/4 enabled"

        await pilot.press("escape")
        await pilot.pause()

        assert not app.query(Panel)
        assert prompt.display
        assert app.focused is prompt

    _run(app, scenario)


def test_space_toggles_the_highlighted_tool() -> None:
    """Space disables the highlighted tool, skipping headers; again re-enables it."""
    app, engine = _tools_app()

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/tools")
        await pilot.pause()

        await pilot.press("down", "space")
        assert "github__get_me" not in _enabled(engine)
        assert _title(app) == "Tools · 3/4 enabled"

        await pilot.press("space")
        assert "github__get_me" in _enabled(engine)

    _run(app, scenario)


def test_bulk_actions_only_apply_to_the_filtered_tools() -> None:
    """With a filter, ctrl+d disables only the tools shown; ctrl+a enables all."""
    app, engine = _tools_app()

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/tools")
        await pilot.pause()

        await pilot.press(*"delete")
        assert str(app.query_one("#tools-disable", Button).label) == "Disable shown"
        await pilot.press("ctrl+d")
        assert _enabled(engine) == ["web_search", "github__get_me"]
        assert _title(app) == "Tools · 2/4 enabled · 2 shown"

        app.query_one("#tools-filter", Input).value = ""
        await pilot.pause()
        await pilot.press("ctrl+a")
        assert len(_enabled(engine)) == 4

    _run(app, scenario)


def test_disable_all_button_disables_every_tool() -> None:
    """Clicking Disable all with no filter disables every tool."""
    app, engine = _tools_app()

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/tools")
        await pilot.pause()

        await pilot.click("#tools-disable")
        await pilot.pause()

        assert _enabled(engine) == []
        assert engine.tools() and app.query(ToolsPanel)

    _run(app, scenario)


def test_mcp_panel_lists_connected_and_failed_servers() -> None:
    """/mcp shows each server with its status, and escape closes it."""
    servers = [
        McpServerStatus("github", "https://gh/", connected=True, tool_count=42),
        McpServerStatus("notion", "https://no/", connected=False, error="HTTP 401"),
    ]
    engine = Engine(
        Agent(FakeLLM([]), ToolRegistry()),
        Pipeline(),
        EventBus(),
        mcp_servers=servers,
    )
    app = SensaiApp(engine, model="test-model")

    async def scenario(pilot: Pilot[None]) -> None:
        await _send(pilot, "/mcp")
        await pilot.pause()

        panel = app.query_one(McpPanel)
        rows = [str(row.render()) for row in panel.query(".mcp-server")]
        assert str(panel.border_title) == "MCP servers · 1 connected"
        assert rows == [
            "● github   connected   42 tools",
            "✗ notion   failed: HTTP 401",
        ]

        await pilot.press("escape")
        await pilot.pause()
        assert not app.query(Panel)

    _run(app, scenario)


def test_tools_list_fits_a_small_window_and_follows_the_highlight() -> None:
    """In a short window the list shrinks to the room left and scrolls."""
    registry = ToolRegistry()
    for index in range(40):
        registry.register(
            ToolSpec(f"github__tool_{index}", "Do it"), _noop, source="github"
        )
    engine = Engine(
        Agent(FakeLLM([]), registry), Pipeline(), EventBus(), tools=registry
    )
    app = SensaiApp(engine, model="test-model")

    async def run() -> None:
        async with app.run_test(size=(80, 20)) as pilot:
            await _send(pilot, "/tools")
            await pilot.pause()
            panel = app.query_one(ToolsPanel)
            tools = app.query_one(ToolList)

            assert tools.region.height >= 5
            assert panel.region.contains_region(tools.region)

            await pilot.press(*["down"] * 15)
            await pilot.pause()

            assert tools.scroll_y > 0
            assert tools.highlighted is not None
            row = tools.highlighted - tools.scroll_y
            assert 0 <= row < tools.size.height

    asyncio.run(run())


LONG_DESCRIPTION = (
    "Search for GitHub repositories by name, description, readme, topics "
    "or other metadata and return the matches"
)


def _tool_rows(width: int) -> list[str]:
    registry = ToolRegistry()
    registry.register(
        ToolSpec("github__search", f"{LONG_DESCRIPTION}\nMore details."),
        _noop,
        source="github",
    )
    registry.register(ToolSpec("web_search", "Search the web"), _noop)
    engine = Engine(
        Agent(FakeLLM([]), registry), Pipeline(), EventBus(), tools=registry
    )
    app = SensaiApp(engine, model="test-model")
    rows: list[str] = []

    async def run() -> None:
        async with app.run_test(size=(width, 24)) as pilot:
            await _send(pilot, "/tools")
            await pilot.pause()
            tools = app.query_one(ToolList)
            rows.extend(
                tools.render_line(y).text.rstrip() for y in range(tools.size.height)
            )

    asyncio.run(run())
    return [row for row in rows if row]


def test_tool_description_uses_the_whole_width() -> None:
    """A wide terminal shows the description's whole first line."""
    rows = _tool_rows(180)

    assert rows[1] == f"[x] search      {LONG_DESCRIPTION}"
    assert len(rows) == 4


def test_tool_description_is_cut_on_one_line_when_narrow() -> None:
    """A narrow terminal keeps one line per tool and ends it with an ellipsis."""
    rows = _tool_rows(70)

    assert rows[1].startswith("[x] search      Search for GitHub")
    assert rows[1].endswith("…")
    assert len(rows) == 4


def test_tool_description_keeps_off_the_scrollbar() -> None:
    """A cut description ends one column before the scrollbar."""
    registry = ToolRegistry()
    for index in range(40):
        registry.register(ToolSpec(f"tool_{index}", "word " * 40), _noop)
    engine = Engine(
        Agent(FakeLLM([]), registry), Pipeline(), EventBus(), tools=registry
    )
    app = SensaiApp(engine, model="test-model")

    async def run() -> None:
        async with app.run_test(size=(70, 20)) as pilot:
            await _send(pilot, "/tools")
            await pilot.pause()
            tools = app.query_one(ToolList)
            row = tools.render_line(1).text
            ellipsis = tools.region.x + row.index("…")

            assert tools.show_vertical_scrollbar
            assert tools.vertical_scrollbar.region.x - ellipsis >= 2

    asyncio.run(run())
