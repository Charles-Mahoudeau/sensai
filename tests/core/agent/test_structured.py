"""Tests for constrained JSON agent output."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sensai.core.agent.events import TurnCompleted
from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.re_act import ReActAgent
from sensai.core.agent.structured import (
    JsonSchemaOutput,
    StructuredOutputCatalog,
    StructuredOutputError,
    format_structured_output,
)
from sensai.core.errors import ModeUnavailableError
from sensai.core.models import ChatDone, Message, TextDelta
from sensai.core.models.llm import ChatOptions
from sensai.core.tools.builtin import web_search
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.events import AgentEvent


async def _collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Collect all agent events from a run."""
    return [event async for event in events]


def _asks_for_a_thought(options: ChatOptions | None) -> bool:
    """Tell whether a request used the schema of a ReAct step."""
    schema = options.response_schema if options is not None else None
    return schema is not None and {"action": {"const": "answer"}}.items() <= (
        schema["anyOf"][-1]["properties"].items()
    )


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
SHIPPED_PLAN_SCHEMA = json.loads(
    (Path(__file__).parents[3] / "config" / "schemas" / "plan.json").read_text()
)
METHOD_PLAN = (
    '{"title": "Solve x² - 5x + 6 = 0", "steps": [{"title": "Compute the '
    'discriminant", "description": "Read a, b and c.", "notion": "Δ = b² - 4ac"}], '
    '"check": "Put each solution back into the equation."}'
)
METHOD_PLAN_TEXT = (
    "## Solve x² - 5x + 6 = 0\n\n"
    "1. **Compute the discriminant**\n"
    "   Read a, b and c.\n"
    "   *Δ = b² - 4ac*\n\n"
    "**✓** Put each solution back into the equation."
)


def test_react_agent_streams_an_ordinary_answer_without_a_schema() -> None:
    """Ordinary answers remain free-form even when structured output is enabled."""
    llm = FakeLLM(
        [
            # ReAct first asks the model for a private thought, in JSON.
            [TextDelta('{"thought": "All known.", "action": "answer"}'), ChatDone()],
            # Once it can answer, it makes a second, free-form final call.
            [TextDelta("Bonjour"), ChatDone()],
        ]
    )
    structured_output = StructuredOutputCatalog(SCHEMAS)
    agent = ReActAgent(llm, ToolRegistry(), structured_output=structured_output)

    events = asyncio.run(_collect(agent.run((Message.user("Say hello"),))))

    assert events[-2:] == [
        TextDelta("Bonjour"),
        TurnCompleted([Message.assistant("Bonjour")]),
    ]
    assert _asks_for_a_thought(llm.options[0])
    assert llm.options[1:] == [None]


def test_react_agent_does_not_validate_a_free_form_answer() -> None:
    """Outside plan mode, a JSON answer is not checked against any schema."""
    llm = FakeLLM(
        [
            [TextDelta('{"thought": "No tool.", "action": "answer"}'), ChatDone()],
            [TextDelta('{"news": []}'), ChatDone()],
        ]
    )
    agent = ReActAgent(
        llm, ToolRegistry(), structured_output=StructuredOutputCatalog(SCHEMAS)
    )

    events = asyncio.run(_collect(agent.run((Message.user("Find recent news"),))))

    assert events[-1] == TurnCompleted([Message.assistant('{"news": []}')])
    assert _asks_for_a_thought(llm.options[0])
    assert llm.options[1:] == [None]


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


def test_plan_mode_writes_the_method_in_one_call() -> None:
    """Plan mode skips the reasoning steps and asks for the plan schema at once.

    No step means no tool can run, so no tool result can give the answer away.
    """
    llm = FakeLLM([[TextDelta(METHOD_PLAN), ChatDone()]])
    registry = ToolRegistry()
    web_search.register_self(registry)
    agent = ReActAgent(
        llm,
        registry,
        AgentPrompts(thought="THINK {tools}", notes="{thought}", answer="", plan="P"),
        mode="plan",
        structured_output=StructuredOutputCatalog({"plan": SHIPPED_PLAN_SCHEMA}),
    )

    events = asyncio.run(_collect(agent.run((Message.user("Résous x² - 5x + 6 = 0"),))))

    assert llm.options == [ChatOptions(response_schema=SHIPPED_PLAN_SCHEMA)]
    assert llm.tools == [[]]
    # The plan instruction follows the user's message, for this call only.
    assert llm.messages[0][-1] == Message.user("Résous x² - 5x + 6 = 0\n\nP")
    assert events[-2:] == [
        TextDelta(METHOD_PLAN_TEXT),
        TurnCompleted([Message.assistant(METHOD_PLAN_TEXT)]),
    ]


def test_plan_mode_is_refused_without_structured_output() -> None:
    """Without a schema catalog, the agent stays in the default mode."""
    agent = ReActAgent(FakeLLM([]), ToolRegistry())

    with pytest.raises(ModeUnavailableError, match=r"\[structured_output\]"):
        agent.mode = "plan"

    assert agent.mode == "answer"


def test_switching_back_from_plan_mode_reasons_again() -> None:
    """Back in the default mode, the agent thinks and answers in free form."""
    llm = FakeLLM(
        [
            [TextDelta('{"thought": "All known.", "action": "answer"}'), ChatDone()],
            [TextDelta("x = 2 ou x = 3"), ChatDone()],
        ]
    )
    agent = ReActAgent(
        llm, ToolRegistry(), structured_output=StructuredOutputCatalog(SCHEMAS)
    )
    agent.mode = "plan"
    agent.mode = "answer"

    events = asyncio.run(_collect(agent.run((Message.user("Résous"),))))

    assert _asks_for_a_thought(llm.options[0])
    assert llm.options[1:] == [None]
    assert events[-1] == TurnCompleted([Message.assistant("x = 2 ou x = 3")])


def test_a_plan_that_breaks_the_schema_is_an_error() -> None:
    """A reply without the final check is not shown as a plan."""
    llm = FakeLLM([[TextDelta('{"title": "Plan", "steps": []}'), ChatDone()]])
    agent = ReActAgent(
        llm,
        ToolRegistry(),
        mode="plan",
        structured_output=StructuredOutputCatalog({"plan": SHIPPED_PLAN_SCHEMA}),
    )

    with pytest.raises(StructuredOutputError):
        asyncio.run(_collect(agent.run((Message.user("Résous"),))))


def test_the_shipped_plan_schema_fits_the_formatter() -> None:
    """A plan valid under `config/schemas/plan.json` renders without error."""
    value = JsonSchemaOutput(SHIPPED_PLAN_SCHEMA).parse(METHOD_PLAN)

    assert format_structured_output("plan", value) == METHOD_PLAN_TEXT
