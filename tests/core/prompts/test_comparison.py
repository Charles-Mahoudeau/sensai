"""Tests for comparison runs between two prompt versions."""

from __future__ import annotations

import asyncio
import itertools
import json
from datetime import UTC, datetime

import pytest

from sensai.core.models import ChatDone, TextDelta
from sensai.core.models.llm import Usage
from sensai.core.models.prompts import PromptVersion
from sensai.core.prompts import PromptComparison
from sensai.core.prompts.comparison import ComparisonError
from tests.fakes import FakeLLM

V1 = PromptVersion("system", 1, "Be detailed.", datetime(2026, 1, 1, tzinfo=UTC))
V2 = PromptVersion("system", 2, "Be brief.", datetime(2026, 1, 2, tzinfo=UTC))


def _answer(text: str, tokens: int):
    return [TextDelta(text), ChatDone(Usage(completion_tokens=tokens, prompt_tokens=5))]


def _verdict(winner: str):
    return [TextDelta(json.dumps({"winner": winner, "reason": f"{winner} is better"}))]


def _clock(*durations: float):
    """Return a clock whose successive calls are 0 seconds apart, then each duration."""
    ticks = itertools.accumulate(
        itertools.chain.from_iterable((0.0, d) for d in durations)
    )
    return lambda: next(ticks)


def test_metrics_without_judge() -> None:
    """Latency, tokens and length are averaged per version."""
    llm = FakeLLM(
        [
            _answer("a long answer", 40),
            _answer("short", 10),
            _answer("another long answer", 60),
            _answer("tiny", 20),
        ]
    )
    comparison = PromptComparison(llm, _clock(3.0, 1.0, 5.0, 1.0))

    report = asyncio.run(comparison.compare(V1, V2, ["q1", "q2"]))

    assert (report.a.version, report.b.version) == (1, 2)
    assert report.a.mean_latency == pytest.approx(4.0)
    assert report.b.mean_latency == pytest.approx(1.0)
    assert report.a.mean_completion_tokens == 50
    assert report.b.mean_completion_tokens == 15
    assert report.b.mean_length == pytest.approx(4.5)
    assert not report.judged
    assert report.results[0].winner is None


def test_each_version_is_sent_as_the_system_message() -> None:
    """Each answer uses its version's content as the system prompt."""
    llm = FakeLLM([_answer("x", 1), _answer("y", 1)])

    asyncio.run(PromptComparison(llm, _clock(1, 1)).compare(V1, V2, ["Hello"]))

    assert [m.content for m in llm.messages[0]] == ["Be detailed.", "Hello"]
    assert [m.content for m in llm.messages[1]] == ["Be brief.", "Hello"]


def test_judge_agreement_counts_as_a_win() -> None:
    """When both orders agree, the winning version gets the point."""
    # Second verdict sees the answers swapped, so "B" there means v1 again.
    llm = FakeLLM([_answer("x", 1), _answer("y", 1), _verdict("A"), _verdict("B")])

    report = asyncio.run(
        PromptComparison(llm, _clock(1, 1)).compare(
            V1, V2, ["q"], judge_prompt="Judge."
        )
    )

    assert (report.a.wins, report.b.wins, report.ties) == (1, 0, 0)
    assert report.results[0].winner == "A"
    assert report.results[0].reasons == ("A is better", "B is better")


def test_judge_disagreement_is_a_tie() -> None:
    """When the verdict follows the position, not the answer, it's a tie."""
    llm = FakeLLM([_answer("x", 1), _answer("y", 1), _verdict("A"), _verdict("A")])

    report = asyncio.run(
        PromptComparison(llm, _clock(1, 1)).compare(
            V1, V2, ["q"], judge_prompt="Judge."
        )
    )

    assert (report.a.wins, report.b.wins, report.ties) == (0, 0, 1)


def test_judge_uses_structured_output_and_the_judge_prompt() -> None:
    """The judge call sends the judge prompt with a JSON schema at temperature 0."""
    llm = FakeLLM([_answer("x", 1), _answer("y", 1), _verdict("A"), _verdict("B")])

    asyncio.run(
        PromptComparison(llm, _clock(1, 1)).compare(
            V1, V2, ["q"], judge_prompt="Judge."
        )
    )

    options = llm.options[2]
    assert llm.messages[2][0].content == "Judge."
    assert options is not None
    assert options.temperature == 0.0
    assert options.response_schema is not None


def test_unreadable_verdict_is_a_tie() -> None:
    """A verdict that isn't the expected JSON doesn't crash the run."""
    llm = FakeLLM(
        [_answer("x", 1), _answer("y", 1), [TextDelta("A, clearly")], _verdict("B")]
    )

    report = asyncio.run(
        PromptComparison(llm, _clock(1, 1)).compare(
            V1, V2, ["q"], judge_prompt="Judge."
        )
    )

    assert report.ties == 1
    assert report.results[0].reasons[0].startswith("unreadable verdict")


def test_no_inputs_is_an_error() -> None:
    """A comparison without inputs is refused."""
    comparison = PromptComparison(FakeLLM([]), _clock())

    with pytest.raises(ComparisonError, match="at least one input"):
        asyncio.run(comparison.compare(V1, V2, []))


@pytest.mark.parametrize("winner", ['["A"]', '{"x": 1}', "1", "null"])
def test_non_string_winner_is_a_tie(winner: str) -> None:
    """A winner that isn't one of the expected strings doesn't crash the run."""
    llm = FakeLLM(
        [
            _answer("x", 1),
            _answer("y", 1),
            [TextDelta(f'{{"winner": {winner}, "reason": "r"}}')],
            _verdict("B"),
        ]
    )

    report = asyncio.run(
        PromptComparison(llm, _clock(1, 1)).compare(
            V1, V2, ["q"], judge_prompt="Judge."
        )
    )

    assert report.ties == 1
    assert report.results[0].reasons[0].startswith("unknown winner")
