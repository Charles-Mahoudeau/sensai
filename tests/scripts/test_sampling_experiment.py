"""Tests for the parts of the sampling experiment that need no model."""

from __future__ import annotations

import pytest

from scripts.sampling_experiment import (
    QUESTIONS,
    Result,
    question_table,
    recall_is_right,
    recall_messages,
    summary_table,
)

CHECKS = {question.name: question.is_right for question in QUESTIONS}


@pytest.mark.parametrize(
    ("name", "answer", "right"),
    [
        ("product", "Le résultat est 121 932 631 112 635 269.", True),
        ("product", "Le résultat est 121932631112635000.", False),
        ("speed", "Sa vitesse moyenne est de 72 km/h.", True),
        ("derivative", "On trouve f'(2) = -6.", True),
        ("derivative", "On trouve f'(2) = \u22126", True),
        ("derivative", "On trouve f'(2) = -16.", False),
        ("roots", "Les racines sont 1, 2 et 3.", True),
        ("roots", "Les racines sont 1 et 2.", False),
        ("limit", r"La limite vaut \(e^2\).", True),
        ("limit", "La limite vaut e.", False),
        ("dice", r"La probabilité est \(\frac{1}{6}\).", True),
        ("dice", "La probabilité est 1/12.", False),
    ],
)
def test_checkers_recognize_right_and_wrong_answers(
    name: str, answer: str, right: bool
) -> None:
    """Each checker accepts the usual ways to write the right answer."""
    assert CHECKS[name](answer) is right


def test_recall_puts_the_fact_first_and_the_question_last() -> None:
    """The fact opens the conversation, so a small context drops it first."""
    messages = recall_messages()

    assert "k = 7.31" in messages[0].content
    assert messages[-1].content.endswith("k ?")
    assert recall_is_right("Ta constante vaut k = 7,31.")
    assert not recall_is_right("Je ne connais pas k.")


def test_tables_count_right_and_distinct_answers() -> None:
    """Accuracy and spread are computed per setting, then per question."""
    results = [
        Result("speed", 0.0, "72 km/h", right=True, seconds=2),
        Result("speed", 0.0, "72 km/h", right=True, seconds=4),
        Result("speed", 1.5, "72 km/h", right=True, seconds=2),
        Result("speed", 1.5, "75 km/h", right=False, seconds=2),
    ]

    assert summary_table(results, "temperature").splitlines()[2:] == [
        "| 0 | 2/2 (100%) | 1.0 | 3 s |",
        "| 1.5 | 1/2 (50%) | 2.0 | 2 s |",
    ]
    assert question_table(results).splitlines()[2] == "| speed | 2/2 | 1/2 |"
