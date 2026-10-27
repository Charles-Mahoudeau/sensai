"""Tests for the ReAct agent's use of its prompts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.agent.events import TurnCompleted
from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, TextDelta, ToolCall
from sensai.core.models.llm import ThinkingDelta, ToolCallRequest
from sensai.core.tools.builtin import web_search
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from sensai.core.agent.events import AgentEvent

PROMPTS = AgentPrompts(
    thought="THINK with {tools}. Say I am ready to answer.",
    notes=" NOTES: {thought}",
    answer="ANSWER NOW",
)
HISTORY = (Message.system("SYSTEM"), Message.user("Latest Python?"))

# Thought, tool call, "ready" thought, final answer: uses all three prompts.
TOOL_TURN = [
    [TextDelta('{"thought": "I need fresh data.", "ready": false}')],
    [ToolCallRequest(ToolCall("web_search", {"query": "python"}, id="c1"))],
    [TextDelta('{"thought": "All known.", "ready": true}')],
    [TextDelta("Python 3.14.")],
]


@pytest.fixture(autouse=True)
def offline_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the web search handler, so no test hits the network."""

    async def search(args: Mapping[str, Any]) -> str:
        del args
        return "1. Python 3.14 - https://python.org - released"

    monkeypatch.setattr(web_search, "_web_search", search)


def _tools() -> ToolRegistry:
    registry = ToolRegistry()
    web_search.register_self(registry)
    return registry


def _run(agent: ReActAgent) -> list[AgentEvent]:
    async def collect() -> list[AgentEvent]:
        return [event async for event in agent.run(HISTORY)]

    return asyncio.run(collect())


def _agent(llm: FakeLLM, prompts: AgentPrompts | None = None) -> ReActAgent:
    """Build a ReAct agent with the web tool used by these prompt tests."""
    registry = ToolRegistry()
    web_search.register_self(registry)
    return ReActAgent(llm, registry, prompts=prompts)


def test_injected_prompts_build_every_request() -> None:
    """Thought, notes and answer requests use the injected texts."""
    llm = FakeLLM(TOOL_TURN)

    _run(ReActAgent(llm, _tools(), PROMPTS))

    thought, act, ready_thought, answer = llm.messages
    assert thought[-1].content.startswith("THINK with - web_search: ")
    assert act[-1] == Message.user("Latest Python? NOTES: I need fresh data.")
    assert ready_thought[-1].content.startswith("THINK with")
    assert answer[-1] == Message.user("ANSWER NOW")


def test_agent_adds_no_system_message() -> None:
    """Every request starts with the caller's system message, and only that."""
    llm = FakeLLM(TOOL_TURN)

    _run(ReActAgent(llm, _tools(), PROMPTS))

    for request in llm.messages:
        assert [m for m in request if m.role == "system"] == [HISTORY[0]]


def test_defaults_are_used_without_prompts() -> None:
    """Without injected prompts, the agent uses the shipped defaults."""
    llm = FakeLLM(TOOL_TURN)
    defaults = AgentPrompts.defaults()

    _run(ReActAgent(llm, _tools()))

    assert llm.messages[0][-1].content.startswith(defaults.thought[:40])
    assert llm.messages[3][-1] == Message.user(defaults.answer)


def test_a_ready_thought_gets_the_answer_without_tools() -> None:
    """`"ready": true` in the JSON thought skips the tools, whatever its language."""
    llm = FakeLLM(
        [
            [TextDelta('{"thought": "Je sais déjà tout.", "ready": true}')],
            [TextDelta("Python 3.14.")],
        ]
    )

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert llm.options[0] is not None
    assert llm.options[0].response_schema is not None
    assert llm.tools[1] == []
    assert llm.messages[1][-1] == HISTORY[-1]
    assert [e for e in events if isinstance(e, ThinkingDelta)] == [
        ThinkingDelta(""),
        ThinkingDelta("Je sais déjà tout."),
        ThinkingDelta("", ready=True),
    ]


def test_a_thought_that_is_not_json_is_not_ready() -> None:
    """The old "I am ready to answer." sentence alone no longer ends the search."""
    llm = FakeLLM([[TextDelta("I am ready to answer.")], [TextDelta("Python 3.14.")]])

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert [spec.name for spec in llm.tools[1]] == ["web_search"]
    assert ThinkingDelta("I am ready to answer.") in events


def test_a_json_only_reply_to_the_tools_is_asked_again_without_them() -> None:
    """Pushed to call a tool, a small model may write `{}`: it is never shown."""
    llm = FakeLLM(
        [
            [TextDelta('{"thought": "I may search.", "ready": false}')],
            [TextDelta("{}\n{}\n{}")],
            [TextDelta("Bonjour.")],
        ]
    )

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Bonjour."
    assert llm.tools[2] == []
    assert events[-1] == TurnCompleted([Message.assistant("Bonjour.")])


def test_a_reply_opening_with_json_is_asked_again_without_tools() -> None:
    """`{}` followed by text is a botched call too, not an answer."""
    llm = FakeLLM(
        [
            [TextDelta('{"thought": "I may search.", "ready": false}')],
            [TextDelta("{}\n \nWhat you remember about the user: (unknown)")],
            [TextDelta("C'est oublié.")],
        ]
    )

    events = _run(ReActAgent(llm, _tools(), PROMPTS))

    assert events[-1] == TurnCompleted([Message.assistant("C'est oublié.")])


def test_a_json_answer_without_tools_is_kept() -> None:
    """Once ready, a JSON answer is what the user asked for: it is shown."""
    llm = FakeLLM(
        [[TextDelta('{"thought": "Easy.", "ready": true}')], [TextDelta('{"a": 1}')]]
    )

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
        '.", "ready": true}',
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
    assert llm.tools[1] == []
