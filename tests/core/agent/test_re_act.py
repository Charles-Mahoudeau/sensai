"""Tests for the ReAct agent's use of its prompts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, TextDelta, ToolCall
from sensai.core.models.llm import ToolCallRequest
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
    [TextDelta("I need fresh data.")],
    [ToolCallRequest(ToolCall("web_search", {"query": "python"}, id="c1"))],
    [TextDelta("I am ready to answer.")],
    [TextDelta("Python 3.14.")],
]


@pytest.fixture(autouse=True)
def offline_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the web search handler, so no test hits the network."""

    async def search(args: Mapping[str, Any]) -> str:
        del args
        return "1. Python 3.14 - https://python.org - released"

    monkeypatch.setattr(web_search, "_web_search", search)


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

    _run(_agent(llm, PROMPTS))

    thought, act, ready_thought, answer = llm.messages
    assert thought[-1].content.startswith("THINK with - web_search: ")
    assert act[-1] == Message.user("Latest Python? NOTES: I need fresh data.")
    assert ready_thought[-1].content.startswith("THINK with")
    assert answer[-1] == Message.user("ANSWER NOW")


def test_agent_adds_no_system_message() -> None:
    """Every request starts with the caller's system message, and only that."""
    llm = FakeLLM(TOOL_TURN)

    _run(_agent(llm, PROMPTS))

    for request in llm.messages:
        assert [m for m in request if m.role == "system"] == [HISTORY[0]]


def test_defaults_are_used_without_prompts() -> None:
    """Without injected prompts, the agent uses the shipped defaults."""
    llm = FakeLLM(TOOL_TURN)
    defaults = AgentPrompts.defaults()

    _run(_agent(llm))

    assert llm.messages[0][-1].content.startswith(defaults.thought[:40])
    assert llm.messages[3][-1] == Message.user(defaults.answer)
