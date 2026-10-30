"""Tests for decoding the streamed JSON thought of the ReAct agent."""

from __future__ import annotations

from sensai.core.agent.thought_stream import ThoughtStream


def _decode(*chunks: str) -> list[str]:
    stream = ThoughtStream()
    return [stream.feed(chunk) for chunk in chunks]


def test_nothing_is_shown_before_the_thought_string_opens() -> None:
    """The keys and spacing before the value give no text."""
    assert _decode('{ "tho', 'ught" :', ' "Bon', "jour") == ["", "", "Bon", "jour"]


def test_escapes_are_decoded_even_when_cut_between_chunks() -> None:
    """A split escape waits for the rest of it, then gives its character."""
    chunks = ('{"thought": "d\\u00', "e9j\\u00e0 \\", '"x\\" \\n\\ud83d', "\\ude00")

    assert _decode(*chunks) == ["d", "éjà ", '"x" \n', "😀"]


def test_the_closing_quote_ends_the_thought() -> None:
    """What follows the thought, such as the action, is never shown."""
    assert _decode('{"thought": "Fini.", "action": "answer"', "}") == ["Fini.", ""]


def test_a_reply_that_is_not_the_json_thought_shows_nothing() -> None:
    """Free text is left to the agent, which shows it whole at the end."""
    assert _decode("I am ready to answer.") == [""]
