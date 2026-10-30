"""Calculator tool evaluating arithmetic expressions."""

import math
import operator
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from mathparse import mathparse, mathwords

from sensai.core.models import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sensai.core.tools.registry import ToolRegistry

type _Number = int | float | Decimal

_MAX_RESULT_DIGITS = 4000
# A float carries about 15 exact significant digits: a larger non-integer
# result can't be exact, so it is rounded to that many.
_SIGNIFICANT_DIGITS = 15
_SCIENTIFIC_FROM = Decimal(10) ** _SIGNIFICANT_DIGITS

_ARITHMETIC: dict[str, Callable[[Any, Any], _Number]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
}


def register_self(tool_registry: ToolRegistry) -> None:
    """Registers the calculator tool into a tool registry."""
    tool_registry.register(
        ToolSpec(
            name="calculator",
            description=(
                "Evaluates an arithmetic expression and returns its result, "
                "exact after '=' or rounded after '≈' when it is too large. "
                "Use it for any calculation instead of computing it yourself. "
                "Supports + - * /, ^ for powers, parentheses, sqrt, log and the "
                "constants pi and e, e.g. '(2 + 3) ^ 2 / sqrt 16'. "
                "It does not solve equations: no unknowns like x and no '='."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "The arithmetic expression to evaluate, e.g. '2 ^ 10 / 3'."
                        ),
                    },
                },
                "required": ["expression"],
            },
            requires_confirmation=False,
        ),
        handler=_calculator,
    )


def _to_postfix(expression: str) -> list[str]:
    """Normalize an expression and convert it to mathparse postfix tokens."""
    expression = expression.replace("**", "^")
    tokens = mathparse.tokenize(expression)
    tokens = mathparse.preprocess_unary_operators(tokens)
    return mathparse.to_postfix(tokens)


def _number(value: str | _Number) -> _Number:
    """Convert a raw number token to a number, leaving numbers unchanged."""
    if not isinstance(value, str):
        return value
    number = mathparse.to_number(value)
    if isinstance(number, str):
        raise ValueError(f"Not a number: {value!r}.")
    return number


def _coerce(a: _Number, b: _Number) -> tuple[_Number, _Number]:
    """Turn a float into a Decimal when the other operand is one."""
    if isinstance(a, Decimal) and isinstance(b, float):
        return a, Decimal(repr(b))
    if isinstance(a, float) and isinstance(b, Decimal):
        return Decimal(repr(a)), b
    return a, b


def _power(a: _Number, b: _Number) -> _Number:
    """Raise `a` to `b`, refusing results too large to compute quickly."""
    if a != 0:
        magnitude = math.log10(abs(a))
        grows = (magnitude > 0) == (b > 0)
        if magnitude and grows and abs(b) > _MAX_RESULT_DIGITS / abs(magnitude):
            raise ValueError(
                f"Result too large: more than {_MAX_RESULT_DIGITS} digits."
            )
    return operator.pow(a, b)


def _apply(token: str, a: str | _Number, b: str | _Number) -> _Number:
    """Apply a binary operator to two operands."""
    if token == ".":
        return Decimal(f"{a}.{b}")
    left, right = _coerce(_number(a), _number(b))
    if token == "/":
        if right == 0:
            raise ZeroDivisionError("Division by zero.")
        return Decimal(str(left)) / Decimal(str(right))
    if token == "^":
        return _power(left, right)
    return _ARITHMETIC[token](left, right)


def _evaluate(postfix: list[str]) -> _Number:
    """Evaluate mathparse postfix tokens, guarding against oversized powers.

    Raw number tokens stay strings on the stack until an operator consumes
    them, since the `.` operator needs their exact digits.

    Raises:
        ValueError: The expression has an unsupported term, is malformed, or
            its result is too large.
        ZeroDivisionError: The expression divides by zero.
    """
    stack: list[str | _Number] = []
    try:
        for token in postfix:
            if mathparse.is_int(token) or mathparse.is_float(token):
                stack.append(token)
            elif token in mathwords.CONSTANTS:
                stack.append(mathwords.CONSTANTS[token])
            elif token in mathwords.UNARY_FUNCTIONS:
                operand = _number(stack.pop())
                stack.append(mathwords.UNARY_FUNCTIONS[token](operand))
            elif token in mathwords.BINARY_OPERATORS:
                b, a = stack.pop(), stack.pop()
                stack.append(_apply(token, a, b))
            else:
                raise ValueError(f"Unsupported term: {token!r}.")
    except IndexError:
        raise ValueError("Malformed expression.") from None
    if len(stack) != 1:
        raise ValueError("Malformed expression.")
    return _number(stack[0])


def _format(value: _Number) -> str:
    """Render a result after its `=` sign, or after `≈` when it is rounded.

    Integers stay exact. A large non-integer result went through a float or a
    rounded division, so only its first digits are right: it is written in
    scientific notation instead of as a long, falsely exact integer.
    """
    if isinstance(value, float):
        value = Decimal(repr(value))
    if isinstance(value, Decimal) and abs(value) >= _SCIENTIFIC_FROM:
        mantissa, exponent = f"{value:.{_SIGNIFICANT_DIGITS - 1}e}".split("e")
        return f"≈ {mantissa.rstrip('0').rstrip('.')}e{exponent}"
    return f"= {_format_exact(value)}"


def _format_exact(value: _Number) -> str:
    """Render a result without trailing zeros or a useless decimal part."""
    if isinstance(value, Decimal):
        value = value.normalize()
        if value == value.to_integral_value():
            return str(int(value))
        return format(value, "f")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


async def _calculator(args: Mapping[str, Any]) -> str:
    expression = str(args.get("expression") or "").strip()
    if not expression:
        raise ValueError("The expression must not be empty.")

    # Restating the expression ties the result to the question for small models.
    return f"{expression} {_format(_evaluate(_to_postfix(expression)))}"
