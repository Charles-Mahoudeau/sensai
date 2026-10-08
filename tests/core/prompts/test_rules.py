"""Tests for the checks applied to new prompt versions."""

from __future__ import annotations

import pytest

from sensai.core.errors import SensaiError
from sensai.core.prompts import (
    JUDGE,
    REACT_NOTES,
    REACT_THOUGHT,
    SYSTEM,
    InvalidPromptError,
    validate,
)

THOUGHT = "Tools: {tools}\nIf done, write: I am ready to answer."


def test_valid_templates_pass() -> None:
    """Templates with exactly their placeholders and phrases are accepted."""
    validate(REACT_THOUGHT, THOUGHT)
    validate(REACT_NOTES, "\n[Notes: {thought}]")


def test_missing_placeholder_is_rejected() -> None:
    """The code fills `{tools}` in; a version without it would lose the tools."""
    with pytest.raises(InvalidPromptError, match=r"must contain \{tools\}"):
        validate(REACT_THOUGHT, "Think. I am ready to answer.")


def test_unknown_placeholder_is_rejected() -> None:
    """A field the code doesn't fill in would crash `str.format`."""
    with pytest.raises(InvalidPromptError, match=r"unknown \{user\}"):
        validate(REACT_NOTES, "{thought} for {user}")


@pytest.mark.parametrize("field", ["thought[999]", "thought.upper", "thought[0].x"])
def test_indexed_or_attribute_fields_are_rejected(field: str) -> None:
    """Only the exact placeholder is allowed: `str.format` would crash on these."""
    with pytest.raises(InvalidPromptError, match="unknown"):
        validate(REACT_NOTES, f"\n[{{thought}} {{{field}}}]")


def test_malformed_braces_are_rejected() -> None:
    """A lone brace would crash `str.format`; the error says how to escape it."""
    with pytest.raises(InvalidPromptError, match=r"malformed braces.*\{\{"):
        validate(REACT_NOTES, "{thought} and a { brace")


def test_escaped_braces_are_allowed() -> None:
    """Literal braces written as `{{ }}` are fine in a template."""
    validate(REACT_NOTES, '{thought} {{"json": true}}')


def test_required_phrase_is_checked_ignoring_case() -> None:
    """`_is_ready()` relies on the phrase the thought prompt asks for."""
    validate(REACT_THOUGHT, "{tools} I AM READY TO ANSWER.")
    with pytest.raises(InvalidPromptError, match="ready to answer"):
        validate(REACT_THOUGHT, "{tools} Say: done.")


def test_untemplated_prompts_accept_any_text() -> None:
    """Prompts sent as they are have no rule: braces included."""
    validate(JUDGE, 'Reply with {"winner": "A"}')
    validate(SYSTEM, "Anything { goes }")
    validate("unknown_prompt", "{whatever}")


def test_invalid_prompt_error_is_a_sensai_error() -> None:
    """Callers that handle `SensaiError` also handle invalid prompts."""
    assert issubclass(InvalidPromptError, SensaiError)
