"""Tests for the session titler."""

from __future__ import annotations

import asyncio

import pytest

from sensai.core.agent.session_title import SessionTitler
from sensai.core.models import TextDelta
from sensai.core.ports import LLMUnavailableError
from tests.fakes import FakeLLM


def _title(*turn: TextDelta | Exception) -> tuple[str | None, FakeLLM]:
    llm = FakeLLM([list(turn)])
    title = asyncio.run(SessionTitler(llm).title_for("Hello", "Hi there"))
    return title, llm


def test_the_exchange_is_sent_after_the_prompt() -> None:
    """The model sees both sides of the exchange, with thinking off."""
    _, llm = _title(TextDelta("Greeting"))

    system, user = llm.messages[0]
    assert system.role == "system"
    assert "User: Hello" in user.content
    assert "Assistant: Hi there" in user.content
    assert llm.options[0] is not None
    assert llm.options[0].think is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Greeting", "Greeting"),
        ('  "Greeting."  ', "Greeting"),
        ("Title: Greeting!", "Greeting"),
        ("Greeting\nA second line", "Greeting"),
        ("   ", None),
    ],
)
def test_the_reply_is_cleaned_up(raw: str, expected: str | None) -> None:
    """Quotes, final punctuation and extra lines are dropped."""
    title, _ = _title(TextDelta(raw))

    assert title == expected


def test_a_long_title_is_cut() -> None:
    """A title never grows past the column width."""
    title, _ = _title(TextDelta("word " * 40))

    assert title is not None
    assert len(title) == 60
    assert title.endswith("…")


def test_a_model_failure_gives_no_title() -> None:
    """The error is swallowed."""
    title, _ = _title(LLMUnavailableError("down"))

    assert title is None
