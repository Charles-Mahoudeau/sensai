"""Tests for the default prompts shipped with the code."""

from __future__ import annotations

import pytest

from sensai.core.prompts import (
    JUDGE,
    MEMORY_EXTRACTION,
    MEMORY_RECALL,
    REACT_ANSWER,
    REACT_NOTES,
    REACT_THOUGHT,
    SYSTEM,
    load_defaults,
    validate,
)

ALL = {
    SYSTEM,
    JUDGE,
    REACT_THOUGHT,
    REACT_NOTES,
    REACT_ANSWER,
    MEMORY_EXTRACTION,
    MEMORY_RECALL,
}


def test_every_default_is_shipped() -> None:
    """All defaults load, keyed by file name, with non-empty text."""
    defaults = load_defaults()

    assert defaults.keys() == ALL
    assert all(text.strip() for text in defaults.values())


@pytest.mark.parametrize("name", sorted(ALL))
def test_every_default_passes_its_rule(name: str) -> None:
    """A shipped default can't break the code that formats it."""
    validate(name, load_defaults()[name])


@pytest.mark.parametrize(
    ("name", "start", "end"),
    [
        (SYSTEM, "You are an AI assistant", ".\n"),
        (REACT_THOUGHT, "Before answering", "small talk.\n"),
        (REACT_NOTES, "\n[Private notes", "{thought}]"),
        (REACT_ANSWER, "Answer the user's request", "short one."),
        (MEMORY_EXTRACTION, "You maintain the long-term memory", ":\n{memories}"),
        (MEMORY_RECALL, "What you remember about the user", "conversations:"),
    ],
)
def test_defaults_keep_their_exact_boundaries(name: str, start: str, end: str) -> None:
    """Texts are sent byte for byte: no newline added or removed at the edges.

    The notes are appended right after the user's message, so a missing leading
    newline or an extra trailing one would change what the model reads.
    """
    text = load_defaults()[name]

    assert text.startswith(start)
    assert text.endswith(end)
    assert not text.endswith("\n\n")


def test_judge_default_asks_for_the_json_verdict() -> None:
    """The judge prompt describes the verdict format the comparison parses."""
    assert '"winner"' in load_defaults()[JUDGE]


def test_memory_maintenance_rules_are_in_the_agent_prompts() -> None:
    """The default prompts tell ReAct how to retrieve and maintain memories."""
    defaults = load_defaults()

    assert "memory_read" in defaults[REACT_THOUGHT]
    assert "saved to memory" in defaults[REACT_THOUGHT]
    assert "memory tools" in defaults[SYSTEM]
    assert "automatically" in defaults[SYSTEM]


def test_memory_extraction_lists_the_memories_after_the_instructions() -> None:
    """The memories fill the end of the prompt; the JSON examples stay literal."""
    text = load_defaults()[MEMORY_EXTRACTION].format(memories="- ville: Lyon")

    assert text.endswith("Existing memories:\n- ville: Lyon")
    assert '{"facts": [], "forget": []}' in text
