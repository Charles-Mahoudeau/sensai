"""Tests for the ReAct agent's steps, prompts and answer."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from sensai.core.agent import AgentError
from sensai.core.agent.events import ToolRunFinished, ToolRunStarted, TurnCompleted
from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, TextDelta, ThinkingEffort
from sensai.core.models.llm import ChatOptions, ThinkingDelta
from sensai.core.models.sandbox import CodeRun
from sensai.core.ports import LLMResponseError
from sensai.core.tools.builtin import python, web_search
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeCodeRunner, FakeLLM

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from sensai.core.agent.events import AgentEvent

PROMPTS = AgentPrompts(
    thought='THINK with {tools}. Say "answer" when done.',
    notes=" NOTES: {thought}",
    answer="ANSWER NOW",
)
HISTORY = (Message.system("SYSTEM"), Message.user("Latest Python?"))


def _step(thought: str, action: str = "answer", **arguments: Any) -> list[TextDelta]:
    """Script one step reply, as the model writes it under the step schema."""
    data: dict[str, Any] = {"thought": thought, "action": action}
    if action != "answer":
        data["arguments"] = arguments
    return [TextDelta(json.dumps(data, ensure_ascii=False))]


# Search, then answer: one tool step, one answer step, the answer.
TOOL_TURN = [
    _step("I need fresh data.", "web_search", query="python"),
    _step("All known."),
    [TextDelta("Python 3.14.")],
]


@pytest.fixture
def searches(monkeypatch: pytest.MonkeyPatch) -> list[Mapping[str, Any]]:
    """Replace the web search handler: no network, and every search is recorded."""
    calls: list[Mapping[str, Any]] = []

    async def search(args: Mapping[str, Any]) -> str:
        calls.append(args)
        return "1. Python 3.14 - https://python.org - released"

    monkeypatch.setattr(web_search, "_web_search", search)
    return calls


def _tools() -> ToolRegistry:
    registry = ToolRegistry()
    web_search.register_self(registry)
    return registry


def _run(agent: ReActAgent) -> list[AgentEvent]:
    async def collect() -> list[AgentEvent]:
        return [event async for event in agent.run(HISTORY)]

    return asyncio.run(collect())


def _schema(options: ChatOptions | None) -> Mapping[str, Any]:
    assert options is not None
    assert options.response_schema is not None
    return options.response_schema


def _actions(options: ChatOptions | None) -> list[str]:
    """The actions a step request allows, from its schema."""
    return [
        branch["properties"]["action"]["const"] for branch in _schema(options)["anyOf"]
    ]


@pytest.mark.usefixtures("searches")
def test_injected_prompts_build_every_request() -> None:
    """Thoughts carry the notes so far; the answer request carries them all."""
    llm = FakeLLM(TOOL_TURN)

    _run(ReActAgent(llm, _tools(), PROMPTS))

    first, second, answer = llm.messages
    assert first[-1].content.startswith("THINK with - web_search: ")
    assert "  arguments: query (string, required)" in first[-1].content
    assert second[-1].content.endswith(" NOTES: I need fresh data.")
    assert answer[-1] == Message.user(
        "ANSWER NOW NOTES: 1. I need fresh data.\n2. All known."
    )


@pytest.mark.usefixtures("searches")
def test_agent_adds_no_system_message() -> None:
    """Every request starts with the caller's system message, and only that."""
    llm = FakeLLM(TOOL_TURN)

    _run(ReActAgent(llm, _tools(), PROMPTS))

    for request in llm.messages:
        assert [m for m in request if m.role == "system"] == [HISTORY[0]]


@pytest.mark.usefixtures("searches")
def test_defaults_are_used_without_prompts() -> None:
    """Without injected prompts, the agent uses the shipped defaults."""
    llm = FakeLLM(TOOL_TURN)
    defaults = AgentPrompts.defaults()

    _run(ReActAgent(llm, _tools()))

    assert llm.messages[0][-1].content.startswith(defaults.thought[:40])
    assert llm.messages[2][-1].content.startswith(defaults.answer)


def test_a_tool_step_runs_its_call_and_records_it(
    searches: list[Mapping[str, Any]],
) -> None:
    """The chosen call runs; the next requests see it as a call and its result."""
    llm = FakeLLM(TOOL_TURN)

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert searches == [{"query": "python"}]
    (started,) = [e for e in events if isinstance(e, ToolRunStarted)]
    assert started.call.name == "web_search"
    call, result = llm.messages[2][2:4]
    assert call.tool_calls == (started.call,)
    assert result.role == "tool"
    assert result.content.startswith("1. Python 3.14")
    assert events[-1] == TurnCompleted([Message.assistant("Python 3.14.")])


@pytest.mark.usefixtures("searches")
def test_the_model_is_never_offered_native_tools() -> None:
    """Steps choose tools through their schema; the answer has no tools at all."""
    llm = FakeLLM(TOOL_TURN)

    _run(ReActAgent(llm, _tools(), PROMPTS))

    assert llm.tools == [[], [], []]
    assert _actions(llm.options[0]) == ["web_search", "answer"]
    assert llm.options[2] is None


def test_an_answer_step_hands_its_thought_to_the_answer() -> None:
    """The thought is the answer's notes, and the step is shown as ready."""
    llm = FakeLLM([_step("Je sais déjà tout."), [TextDelta("Python 3.14.")]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    notes = "Latest Python? NOTES: Je sais déjà tout."
    assert llm.messages[1][-1] == Message.user(notes)
    assert [e for e in events if isinstance(e, ThinkingDelta)] == [
        ThinkingDelta(""),
        ThinkingDelta("Je sais déjà tout."),
        ThinkingDelta("", ready=True),
    ]
    shown = [e for e in events if isinstance(e, TextDelta)]
    assert shown == [TextDelta("Python 3.14.")]


def test_a_reply_that_is_not_a_step_is_shown_whole_then_answered() -> None:
    """A reply cut short, or not JSON, ends the thoughts instead of looping."""
    llm = FakeLLM([[TextDelta("I am ready")], [TextDelta("Python 3.14.")]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert ThinkingDelta("I am ready", ready=True) in events
    assert events[-1] == TurnCompleted([Message.assistant("Python 3.14.")])


CUT = "Pour être précis sur l'origine du terme"


def test_an_answer_forced_by_a_cut_thought_thinks_again() -> None:
    """The cut thought becomes a note, is not tagged ready, and a step follows."""
    llm = FakeLLM([_step(CUT), _step("All known."), [TextDelta("Python 3.14.")]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    closing = [e for e in events if isinstance(e, ThinkingDelta) and not e.text]
    assert [e.ready for e in closing] == [False, False, False, True]
    assert llm.messages[1][-1].content.endswith(f" NOTES: {CUT}")
    assert llm.options[2] is None


def test_a_cut_answer_is_thought_again_once_per_turn() -> None:
    """A model that never ends its sentences answers after one more step."""
    llm = FakeLLM([_step(CUT), _step(CUT), [TextDelta("Python 3.14.")]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert llm.options[2] is None
    assert events[-1] == TurnCompleted([Message.assistant("Python 3.14.")])


def test_a_cut_thought_calling_a_tool_runs_it(
    searches: list[Mapping[str, Any]],
) -> None:
    """A call has concrete arguments: the model chose it, cut or not."""
    llm = FakeLLM(
        [
            _step(CUT, "web_search", query="hyperpop"),
            _step("All known."),
            [TextDelta("Hyperpop.")],
        ]
    )

    _run(ReActAgent(llm, _tools(), PROMPTS))

    assert searches == [{"query": "hyperpop"}]


def test_invalid_arguments_are_not_run(searches: list[Mapping[str, Any]]) -> None:
    """Arguments that break the tool's parameters come back as an error result."""
    llm = FakeLLM(
        [
            _step("Search.", "web_search", query=3),
            _step("Could not search."),
            [TextDelta("Sorry.")],
        ]
    )

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert searches == []
    (finished,) = [e for e in events if isinstance(e, ToolRunFinished)]
    assert finished.result.is_error
    assert "arguments.query must be a string" in finished.result.content
    assert llm.messages[1][3] == Message.tool(
        finished.result.content, "web_search", finished.call.id or ""
    )


def test_a_tool_failing_twice_is_no_longer_offered(
    searches: list[Mapping[str, Any]],
) -> None:
    """After two errors in a turn, the step schema leaves the tool out."""
    llm = FakeLLM(
        [
            _step("Search.", "web_search", query=1),
            _step("Search again.", "web_search", query=2),
            _step("I can't search."),
            [TextDelta("Sorry.")],
        ]
    )

    _run(ReActAgent(llm, _tools(), PROMPTS))

    assert searches == []
    assert _actions(llm.options[1]) == ["web_search", "answer"]
    assert _actions(llm.options[2]) == ["answer"]
    assert "(none)" in llm.messages[2][-1].content


def test_a_search_repeated_with_other_options_answers(
    searches: list[Mapping[str, Any]],
) -> None:
    """Only the required arguments make a call new: a repeat goes to the answer."""
    llm = FakeLLM(
        [
            _step("Search.", "web_search", query="python", max_results=1),
            _step("Search more.", "web_search", query="python", max_results=5),
            [TextDelta("Python 3.14.")],
        ]
    )

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert len(searches) == 1
    assert llm.options[2] is None
    assert events[-1] == TurnCompleted([Message.assistant("Python 3.14.")])


def test_a_call_rejected_for_its_arguments_can_be_retried(
    searches: list[Mapping[str, Any]],
) -> None:
    """A call that didn't run is not a repeat: its correction is run."""
    llm = FakeLLM(
        [
            _step("Search.", "web_search", query="python", max_results="many"),
            _step("Search again.", "web_search", query="python", max_results=5),
            _step("All known."),
            [TextDelta("Python 3.14.")],
        ]
    )

    _run(ReActAgent(llm, _tools(), PROMPTS))

    assert searches == [{"query": "python", "max_results": 5}]


def test_the_budget_ends_with_an_answer(searches: list[Mapping[str, Any]]) -> None:
    """Once the effort's steps are spent, the agent answers with what it has."""
    llm = FakeLLM(
        [
            _step("Search.", "web_search", query="a"),
            _step("Search more.", "web_search", query="b"),
            [TextDelta("Python 3.14.")],
        ]
    )
    agent = ReActAgent(llm, _tools(), PROMPTS)
    agent.thinking_effort = ThinkingEffort.LOW

    events = _run(agent)

    assert len(searches) == ThinkingEffort.LOW.level
    assert llm.options[2] is None
    assert events[-1] == TurnCompleted([Message.assistant("Python 3.14.")])


def test_no_effort_answers_at_once() -> None:
    """Without thinking, the only request is the answer, without notes."""
    llm = FakeLLM([[TextDelta("Python 3.14.")]])
    agent = ReActAgent(llm, _tools(), PROMPTS)
    agent.thinking_effort = ThinkingEffort.NONE

    _run(agent)

    assert llm.messages == [list(HISTORY)]
    assert llm.options == [None]


def test_a_refused_schema_falls_back_to_the_flat_one_for_the_turn(
    searches: list[Mapping[str, Any]],
) -> None:
    """A server refusing `anyOf` gets the flat schema until the turn ends."""
    llm = FakeLLM(
        [
            [LLMResponseError("invalid JSON schema in format")],
            _step("Search.", "web_search", query="python"),
            _step("All known."),
            [TextDelta("Python 3.14.")],
            _step("All known."),
            [TextDelta("Python 3.14.")],
        ]
    )
    agent = ReActAgent(llm, _tools(), PROMPTS)

    _run(agent)
    _run(agent)

    flat = _schema(llm.options[1])
    assert flat["properties"]["action"]["enum"] == ["web_search", "answer"]
    assert _schema(llm.options[2]) == _schema(llm.options[1])
    assert _schema(llm.options[4]) != flat


def test_an_error_after_the_reply_started_is_raised() -> None:
    """Asking again would show the thought twice: the error ends the turn."""
    llm = FakeLLM([[TextDelta('{"thought": "Hm'), LLMResponseError("lost")]])

    with pytest.raises(AgentError, match="lost"):
        _run(ReActAgent(llm, _tools(), PROMPTS))


def test_a_json_answer_is_kept() -> None:
    """The answer is never taken for a tool call: JSON the user asked for is shown."""
    llm = FakeLLM([_step("Easy."), [TextDelta('{"a": 1}')]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert events[-1] == TurnCompleted([Message.assistant('{"a": 1}')])


def test_the_thought_streams_as_its_json_arrives() -> None:
    """Each chunk shows its decoded text, even with an escape cut in two."""
    chunks = [
        '{"thou',
        'ght": "Je sais d\\u00',
        'e9j\\u00e0 \\"',
        'tout\\" \\ud83d',
        "\\ude00",
        '.", "action": "answer"}',
    ]
    llm = FakeLLM([[TextDelta(chunk) for chunk in chunks], [TextDelta("Python.")]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    deltas = [e for e in events if isinstance(e, ThinkingDelta)]
    assert [d.text for d in deltas] == [
        "",
        "Je sais d",
        'éjà "',
        'tout" ',
        "😀",
        ".",
        "",
    ]
    assert deltas[-1].ready
    assert llm.options[1] is None


def test_failing_code_is_fixed_without_the_user() -> None:
    """A traceback goes back to the model, which corrects its code and answers."""
    error = "Traceback (most recent call last):\nNameError: name 'y' is not defined"
    runner = FakeCodeRunner([CodeRun("", error, 1, 0.3), CodeRun("4\n", "", 0, 0.3)])
    registry = ToolRegistry()
    python.register_self(registry, runner)
    llm = FakeLLM(
        [
            _step("Compute it.", "run_python", code="print(y * 2)"),
            _step(
                "y is undefined, define it.", "run_python", code="y = 2\nprint(y * 2)"
            ),
            _step("The result is 4."),
            [TextDelta("The result is 4.")],
        ]
    )

    events = _run(ReActAgent(llm, registry, PROMPTS))

    assert runner.codes == ["print(y * 2)", "y = 2\nprint(y * 2)"]
    seen_by_retry = [m.content for m in llm.messages[1] if m.role == "tool"]
    assert any("NameError" in content for content in seen_by_retry)
    assert events[-1] == TurnCompleted([Message.assistant("The result is 4.")])
