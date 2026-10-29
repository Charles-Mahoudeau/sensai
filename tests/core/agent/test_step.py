"""Tests for the step schema, its parsing and the checks before a call runs."""

from __future__ import annotations

import json

import pytest

from sensai.core.agent.step import (
    ANSWER,
    Step,
    call_key,
    check_arguments,
    flat_step_schema,
    parse_step,
    portable_arguments,
    step_schema,
)
from sensai.core.models import ToolCall, ToolSpec
from sensai.core.tools.builtin.memory import read as memory_read

SEARCH = ToolSpec(
    "web_search",
    "Searches the web.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
)
NO_ARGUMENTS = ToolSpec("get_me", "Returns the current user.")


def test_step_schema_has_a_branch_per_tool_and_the_answer() -> None:
    """Each branch ties an action to its own arguments, the thought first."""
    schema = step_schema([SEARCH, NO_ARGUMENTS])

    search, get_me, answer = schema["anyOf"]
    assert list(search["properties"]) == ["thought", "action", "arguments"]
    assert search["properties"]["action"] == {"const": "web_search"}
    assert search["properties"]["arguments"] == portable_arguments(SEARCH)
    assert get_me["properties"]["arguments"] == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    assert answer["properties"] == {
        "thought": {"type": "string"},
        "action": {"const": ANSWER},
    }
    assert all(branch["additionalProperties"] is False for branch in schema["anyOf"])


def test_step_schema_without_tools_only_allows_the_answer() -> None:
    """With every tool off, a step can only conclude."""
    (answer,) = step_schema([])["anyOf"]

    assert answer["properties"]["action"] == {"const": ANSWER}


def test_flat_step_schema_lists_the_actions_without_any_of() -> None:
    """The fallback uses only the most basic keywords."""
    schema = flat_step_schema([SEARCH])

    assert "anyOf" not in json.dumps(schema)
    assert "const" not in json.dumps(schema)
    assert schema["properties"]["action"]["enum"] == ["web_search", ANSWER]
    assert list(schema["properties"]) == ["thought", "action", "arguments"]


def test_portable_arguments_drop_annotations_and_limits() -> None:
    """Descriptions and minimums go: the check before the call keeps them."""
    assert portable_arguments(SEARCH) == {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def test_portable_arguments_keep_enums_and_nested_items() -> None:
    """Enums and arrays of objects are part of the portable subset."""
    tool = ToolSpec(
        "list_issues",
        "Lists issues.",
        {
            "type": "object",
            "properties": {
                "state": {"type": "string", "enum": ["open", "closed"]},
                "labels": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"name": {}}},
                },
            },
            "required": ["state"],
        },
    )

    assert portable_arguments(tool) == {
        "type": "object",
        "properties": {
            "state": {"type": "string", "enum": ["open", "closed"]},
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {}},
                    "required": [],
                },
            },
        },
        "required": ["state"],
        "additionalProperties": False,
    }


@pytest.mark.parametrize(
    "parameter",
    [
        {"anyOf": [{"type": "string"}, {"type": "null"}]},
        {"$ref": "#/$defs/Owner"},
        {"type": ["string", "null"]},
        {"type": "null"},
        {"type": "string", "enum": ["a", None]},
    ],
)
def test_arguments_beyond_the_portable_subset_accept_any_object(
    parameter: dict[str, object],
) -> None:
    """One parameter a grammar may not support makes the tool's arguments free."""
    tool = ToolSpec(
        "mcp_tool",
        "An MCP tool.",
        {"type": "object", "properties": {"owner": parameter}},
    )

    assert portable_arguments(tool) == {"type": "object"}


def test_a_required_field_without_a_property_accepts_any_object() -> None:
    """A grammar can't declare it, and closing the object would forbid it."""
    tool = ToolSpec(
        "mcp_tool",
        "An MCP tool.",
        {
            "type": "object",
            "properties": {"owner": {"type": "string"}},
            "required": ["owner", "repo"],
        },
    )

    assert portable_arguments(tool) == {"type": "object"}


def test_a_choice_of_required_fields_is_dropped() -> None:
    """`memory_read` needs one of three fields: the rest of its schema is kept."""
    arguments = portable_arguments(memory_read.spec())

    assert set(arguments["properties"]) == {"memory_id", "type", "query", "limit"}
    assert arguments["properties"]["memory_id"] == {"type": "integer"}
    assert "anyOf" not in arguments


def test_parse_step_reads_a_tool_call() -> None:
    """A tool action becomes a call with its arguments and a fresh id."""
    step = parse_step(
        '{"thought": " Search. ", "action": "web_search", '
        '"arguments": {"query": "python"}}',
        [SEARCH],
    )

    assert step.thought == "Search."
    assert step.call is not None
    assert (step.call.name, dict(step.call.arguments)) == (
        "web_search",
        {"query": "python"},
    )
    assert step.call.id is not None
    assert step.call.id.startswith("call_")


def test_parse_step_reads_the_answer() -> None:
    """The answer action has no call."""
    assert parse_step('{"thought": "Done.", "action": "answer"}', [SEARCH]) == Step(
        "Done."
    )


def test_a_flat_answer_ignores_its_arguments() -> None:
    """The flat schema always has arguments: an empty object for the answer."""
    step = parse_step(
        '{"thought": "Done.", "action": "answer", "arguments": {}}', [SEARCH]
    )

    assert step == Step("Done.")


def test_a_call_without_arguments_gets_an_empty_object() -> None:
    """Missing or malformed arguments are no arguments; the check reports them."""
    step = parse_step('{"thought": "Me.", "action": "web_search"}', [SEARCH])

    assert step.call is not None
    assert step.call.arguments == {}


@pytest.mark.parametrize(
    "text",
    [
        '{"thought": "Hm',
        "I am ready to answer.",
        '["web_search"]',
        '{"thought": "Hm.", "action": ["web_search"], "arguments": {}}',
        '{"thought": "Hm.", "action": {}, "arguments": {}}',
        '{"thought": "Hm.", "action": "github__get_me", "arguments": {}}',
    ],
)
def test_a_reply_that_is_not_a_valid_step_is_an_answer(text: str) -> None:
    """Cut off, not JSON, or naming a tool not offered: the agent answers."""
    assert parse_step(text, [SEARCH]).call is None


def test_a_reply_that_is_not_json_keeps_its_text_as_the_thought() -> None:
    """The raw reply is shown in place of the thought it should have held."""
    assert parse_step(" I am ready. ", [SEARCH]) == Step("I am ready.")


def test_check_arguments_accepts_valid_arguments() -> None:
    """Arguments matching the parameters pass."""
    assert check_arguments(SEARCH, {"query": "python", "max_results": 3}) is None


@pytest.mark.parametrize(
    ("arguments", "problem"),
    [
        ({}, "missing required field(s): query"),
        ({"query": 3}, "arguments.query must be a string"),
        ({"query": "x", "max_results": "5"}, "max_results must be an integer"),
        ({"query": "x", "max_results": 50}, "must be at most 10"),
    ],
)
def test_check_arguments_reports_what_is_wrong(
    arguments: dict[str, object], problem: str
) -> None:
    """Limits dropped from the grammar are still enforced here."""
    reported = check_arguments(SEARCH, arguments)

    assert reported is not None
    assert problem in reported


def test_check_arguments_tolerates_keywords_it_does_not_know() -> None:
    """MCP schemas may use any keyword: the tool itself is the last judge."""
    tool = ToolSpec(
        "mcp_tool",
        "An MCP tool.",
        {
            "type": "object",
            "properties": {
                "owner": {"type": ["string", "null"], "minimum": 2},
                "flag": True,
                "page": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
        },
    )

    assert check_arguments(tool, {"owner": None, "flag": 1, "page": "x"}) is None


def test_check_arguments_checks_a_list_of_types() -> None:
    """A value must match one of the listed types, `null` included."""
    tool = ToolSpec(
        "mcp_tool",
        "An MCP tool.",
        {"type": "object", "properties": {"owner": {"type": ["string", "null"]}}},
    )

    assert check_arguments(tool, {"owner": "me"}) is None
    assert check_arguments(tool, {"owner": None}) is None
    assert "arguments.owner must be one of the types" in (
        check_arguments(tool, {"owner": 3}) or ""
    )


def test_check_arguments_rejects_a_property_that_is_false() -> None:
    """`false` allows no value."""
    tool = ToolSpec(
        "mcp_tool",
        "An MCP tool.",
        {"type": "object", "properties": {"forbidden": False}},
    )

    assert "arguments.forbidden is not allowed" in (
        check_arguments(tool, {"forbidden": 1}) or ""
    )
    assert check_arguments(tool, {}) is None


def test_call_key_only_counts_required_arguments() -> None:
    """A search repeated with another result count is the same search."""
    first = ToolCall("web_search", {"query": "python", "max_results": 1}, "c1")
    second = ToolCall("web_search", {"query": "python", "max_results": 5}, "c2")
    other = ToolCall("web_search", {"query": "rust"}, "c3")

    assert call_key(SEARCH, first) == call_key(SEARCH, second)
    assert call_key(SEARCH, first) != call_key(SEARCH, other)


def test_call_key_without_required_arguments_counts_them_all() -> None:
    """A tool without required arguments is identified by all of them."""
    tool = ToolSpec(
        "memory_read",
        "Reads memories.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
    )

    assert call_key(tool, ToolCall("memory_read", {"query": "a"})) != call_key(
        tool, ToolCall("memory_read", {"query": "b"})
    )


@pytest.mark.parametrize(
    ("thought", "cut"),
    [
        ("Pour être plus précis sur l'origine exacte du terme ", True),
        ("I need to search for", True),
        ("I need fresh data.", False),
        ("Ça va ?", False),
        ("Il cite « hyperpop »", False),
        ("", False),
    ],
)
def test_parse_step_tells_a_thought_cut_mid_sentence(thought: str, cut: bool) -> None:
    """A quote closing the string early leaves a thought without its full stop."""
    text = json.dumps({"thought": thought, "action": "answer"})

    assert parse_step(text, [SEARCH]).cut is cut


def test_a_reply_that_is_not_json_is_never_cut() -> None:
    """Only a parsed thought can be cut: a broken reply just ends the thoughts."""
    assert not parse_step('{"thought": "Hm', [SEARCH]).cut
