"""Tests for the calculator tool."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.models import ToolCall
from sensai.core.tools.builtin import calculator
from sensai.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from sensai.core.models import ToolResult


def _calculate(expression: str) -> ToolResult:
    registry = ToolRegistry()
    calculator.register_self(registry)
    return asyncio.run(
        registry.call(ToolCall("calculator", {"expression": expression}, "calc-1"))
    )


def test_calculator_is_registered() -> None:
    """The tool is offered to the model under the `calculator` name."""
    registry = ToolRegistry()
    calculator.register_self(registry)

    (spec,) = registry.spec()
    assert spec.name == "calculator"
    assert spec.parameters["required"] == ["expression"]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3 * 4", "14"),
        ("(2 + 3) * 4", "20"),
        ("10 / 4", "2.5"),
        ("0.1 + 0.2", "0.3"),
        ("2 ^ 10", "1024"),
        ("2 ** 10", "1024"),
        ("2 ^ -2", "0.25"),
        ("sqrt 16", "4"),
        ("log 1000", "3"),
        ("2 ^ 100", str(2**100)),
        ("10 ^ 20 / 4", "25000000000000000000"),
        ("2.5 * 10 ^ 20", "250000000000000000000"),
        (
            "1.2345678901234567890123456789012345",
            "1.2345678901234567890123456789012345",
        ),
    ],
)
def test_calculator_evaluates_expressions(expression: str, expected: str) -> None:
    """Valid expressions return `<expression> = <result>`, `**` read as a power."""
    result = _calculate(expression)

    assert not result.is_error
    assert result.content == f"{expression} = {expected}"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (
            "9998/51659898 * sqrt(546465) * 842^44 + 2 - 6 / 8 * 6",
            "7.40069983123041e+127",
        ),
        ("10 ^ 20 / 3", "3.33333333333333e+19"),
        ("sqrt 2 * 10 ^ 30", "1.4142135623731e+30"),
        ("sqrt 2", "1.4142135623731"),
        ("1 / 3", "0.333333333333333"),
        ("2 ^ -2000", "8.70980981621722e-603"),
        ("0.5 ^ 2000", "8.70980981621722e-603"),
    ],
)
def test_calculator_rounds_inexact_results(expression: str, expected: str) -> None:
    """Rounded results are marked `≈`, small or large, never shown as exact."""
    result = _calculate(expression)

    assert not result.is_error
    assert result.content == f"{expression} ≈ {expected}"


@pytest.mark.parametrize(
    "expression",
    ["9 ^ 9 ^ 9", "10 ^ 4001", "0.5 ^ -100000", "10 ^ 3999 * 10 ^ 3999"],
)
def test_calculator_refuses_oversized_results(expression: str) -> None:
    """Powers and products whose result is too large are refused, not computed."""
    result = _calculate(expression)

    assert result.is_error
    assert "too large" in result.content


def test_calculator_refuses_results_underflowing_to_zero() -> None:
    """A nonzero power too small for a float is an error, not a false zero."""
    result = _calculate("e ^ -800")

    assert result.is_error
    assert "too small" in result.content


@pytest.mark.parametrize("expression", ["1 / 0", "1 / 0 + 1"])
def test_calculator_reports_division_by_zero(expression: str) -> None:
    """Division by zero is an error, even in the middle of an expression."""
    result = _calculate(expression)

    assert result.is_error
    assert "ZeroDivisionError" in result.content


@pytest.mark.parametrize(
    "expression", ["", "   ", "x + 2 = 5", "__import__('os')", "5 +"]
)
def test_calculator_rejects_invalid_expressions(expression: str) -> None:
    """Empty, malformed or non-arithmetic input is reported as an error."""
    assert _calculate(expression).is_error
