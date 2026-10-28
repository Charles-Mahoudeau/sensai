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
    ],
)
def test_calculator_evaluates_expressions(expression: str, expected: str) -> None:
    """Valid expressions return `<expression> = <result>`, `**` read as a power."""
    result = _calculate(expression)

    assert not result.is_error
    assert result.content == f"{expression} = {expected}"


@pytest.mark.parametrize("expression", ["9 ^ 9 ^ 9", "10 ^ 4001", "0.5 ^ -100000"])
def test_calculator_refuses_oversized_powers(expression: str) -> None:
    """Powers whose result is too large are refused instead of computed."""
    result = _calculate(expression)

    assert result.is_error
    assert "too large" in result.content


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
