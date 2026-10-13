"""Tests for constrained JSON agent output."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.agent.events import TurnCompleted
from sensai.core.agent.re_act import ReActAgent
from sensai.core.agent.structured import (
    JsonSchemaOutput,
    StructuredOutputCatalog,
    StructuredOutputError,
)
from sensai.core.models import ChatDone, Message, TextDelta
from sensai.core.models.llm import ChatOptions
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.events import AgentEvent


async def _collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Collect all agent events from a run."""
    return [event async for event in events]


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high"]},
                },
                "required": ["title", "description", "priority"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "steps"],
    "additionalProperties": False,
}
SCHEMAS = {"plan": PLAN_SCHEMA}


def test_react_agent_streams_an_ordinary_answer_without_a_schema() -> None:
    """Ordinary answers remain free-form even when structured output is enabled."""
    llm = FakeLLM(
        [
            # ReAct first asks the model for a private readiness assessment.
            [TextDelta("I am ready to answer."), ChatDone()],
            # Once ready, it makes a second, free-form final call.
            [TextDelta("Bonjour"), ChatDone()],
        ]
    )
    structured_output = StructuredOutputCatalog(SCHEMAS)
    agent = ReActAgent(llm, structured_output=structured_output)

    events = asyncio.run(_collect(agent.run((Message.user("Say hello"),))))

    assert events[-2:] == [
        TextDelta("Bonjour"),
        TurnCompleted([Message.assistant("Bonjour")]),
    ]
    assert llm.options == [None, None]


def test_react_agent_does_not_validate_a_tool_generation_reply() -> None:
    """A reply from the unconstrained tool branch is not parsed as final JSON."""
    llm = FakeLLM(
        [
            [TextDelta("I need a tool."), ChatDone()],
            [TextDelta('{"name":"web_search"}'), ChatDone()],
        ]
    )
    agent = ReActAgent(llm, structured_output=StructuredOutputCatalog(SCHEMAS))

    events = asyncio.run(_collect(agent.run((Message.user("Find recent news"),))))

    assert events[-1] == TurnCompleted([Message.assistant('{"name":"web_search"}')])
    assert llm.options == [None, None]


def test_json_schema_output_validates_nested_plan() -> None:
    """Nested arrays, enums and required properties are checked in the core."""
    output = JsonSchemaOutput(PLAN_SCHEMA)

    # A nested item with the permitted enum value satisfies the plan contract.
    output.validate(
        '{"title":"Plan","steps":[{"title":"Step","description":"Do it",'
        '"priority":"high"}]}'
    )

    # The same shape is rejected when the nested enum value is not permitted.
    with pytest.raises(StructuredOutputError, match="must be one of"):
        output.validate(
            '{"title":"Plan","steps":[{"title":"Step","description":"Do it",'
            '"priority":"low"}]}'
        )


def test_react_agent_uses_plan_schema_in_plan_mode() -> None:
    """Plan mode selects the plan schema without any configuration choice."""
    llm = FakeLLM(
        [
            [TextDelta("I am ready to answer."), ChatDone()],
            [
                TextDelta(
                    '{"title":"Plan the work","steps":[{"title":"Write tests",'
                    '"description":"Cover the new behavior.","priority":"high"}]}'
                ),
                ChatDone(),
            ],
        ]
    )
    agent = ReActAgent(
        llm, mode="plan", structured_output=StructuredOutputCatalog(SCHEMAS)
    )

    events = asyncio.run(_collect(agent.run((Message.user("Plan the work"),))))

    # Mode selection happens in the agent, not in the TOML configuration.
    assert llm.options == [None, ChatOptions(response_schema=PLAN_SCHEMA)]
    assert events[-2:] == [
        TextDelta(
            "## Plan the work\n\n"
            "1. **Write tests** (high priority)\n"
            "   Cover the new behavior."
        ),
        TurnCompleted(
            [
                Message.assistant(
                    "## Plan the work\n\n"
                    "1. **Write tests** (high priority)\n"
                    "   Cover the new behavior."
                )
            ]
        ),
    ]
