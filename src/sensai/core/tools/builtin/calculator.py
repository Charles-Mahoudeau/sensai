"""Calculator tool evaluating arithmetic expressions."""

import math
import operator
from decimal import Context, Decimal, Inexact, localcontext
from typing import TYPE_CHECKING, Any

from mathparse import mathparse, mathwords

from sensai.core.models import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sensai.core.tools.registry import ToolRegistry

type _Number = int | float | Decimal

_MAX_RESULT_DIGITS = 4000
# A float carries about 15 exact significant digits, so a rounded result is
# written with that many.
_SIGNIFICANT_DIGITS = 15
# A rounded result whose exponent falls outside this range is written in
# scientific notation instead of with a long run of zeros.
_FIXED_EXPONENTS = range(-6, _SIGNIFICANT_DIGITS)
# Floats hold every integer below this exactly.
_EXACT_FLOAT_LIMIT = 2.0**53

_ARITHMETIC: dict[str, Callable[[Any, Any], _Number]] = {
    "+": operator.add,
    "-": operator.sub,
}


def register_self(tool_registry: ToolRegistry) -> None:
    """Registers the calculator tool into a tool registry."""
    tool_registry.register(
        ToolSpec(
            name="calculator",
            description=(
                "Evaluates an arithmetic expression and returns its result, "
                "exact after '=' or rounded after '≈'. "
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


def _log10(value: _Number) -> float:
    """Order of magnitude of a nonzero number, leaving the decimal flags alone."""
    if isinstance(value, Decimal):
        # A float can't hold a tiny or huge Decimal, and the current context
        # would record the rounded log as an inexact result.
        return float(value.copy_abs().log10(Context()))
    return math.log10(abs(value))


def _too_large() -> ValueError:
    return ValueError(f"Result too large: more than {_MAX_RESULT_DIGITS} digits.")


def _power(a: _Number, b: _Number) -> _Number:
    """Raise `a` to `b`, refusing results too large to compute quickly.

    Raises:
        ValueError: The result has too many digits, or is too small to be
            told apart from zero.
    """
    if a == 0:
        return operator.pow(a, b)
    magnitude = _log10(a)
    grows = (magnitude > 0) == (b > 0)
    if magnitude and grows and abs(b) > _MAX_RESULT_DIGITS / abs(magnitude):
        raise _too_large()
    if isinstance(a, int) and isinstance(b, int) and b < 0:
        # As a Decimal, `2 ^ -2` stays exact and `2 ^ -2000` does not
        # underflow to a float zero.
        a = Decimal(a)
    result = operator.pow(a, b)
    if result == 0:
        raise ValueError("Result too small: it underflows to zero.")
    return result


def _multiply(a: Any, b: Any) -> _Number:
    """Multiply `a` by `b`, refusing products too large to compute quickly.

    The operands are already coerced to types that multiply together.
    """
    if a and b and _log10(a) + _log10(b) > _MAX_RESULT_DIGITS:
        raise _too_large()
    return operator.mul(a, b)


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
    if token == "*":
        return _multiply(left, right)
    return _ARITHMETIC[token](left, right)


def _is_exact_float(value: _Number) -> bool:
    """Whether a value is not a float, or a float that can't have been rounded.

    A non-integer float comes from a constant, a root or a log, so it is
    taken as rounded.
    """
    if not isinstance(value, float):
        return True
    return value.is_integer() and abs(value) < _EXACT_FLOAT_LIMIT


def _evaluate(postfix: list[str]) -> tuple[_Number, bool]:
    """Evaluate mathparse postfix tokens, guarding against oversized results.

    Raw number tokens stay strings on the stack until an operator consumes
    them, since the `.` operator needs their exact digits.

    Returns:
        The result, and whether it is exact: no step rounded a Decimal or
        produced a rounded float.

    Raises:
        ValueError: The expression has an unsupported term, is malformed, or
            its result is too large or too small.
        ZeroDivisionError: The expression divides by zero.
    """
    stack: list[str | _Number] = []
    exact = True
    with localcontext() as context:
        try:
            for token in postfix:
                if mathparse.is_int(token) or mathparse.is_float(token):
                    stack.append(token)
                    continue
                if token in mathwords.CONSTANTS:
                    value = mathwords.CONSTANTS[token]
                elif token in mathwords.UNARY_FUNCTIONS:
                    operand = _number(stack.pop())
                    value = mathwords.UNARY_FUNCTIONS[token](operand)
                elif token in mathwords.BINARY_OPERATORS:
                    b, a = stack.pop(), stack.pop()
                    value = _apply(token, a, b)
                else:
                    raise ValueError(f"Unsupported term: {token!r}.")
                exact = exact and _is_exact_float(value)
                stack.append(value)
        except IndexError:
            raise ValueError("Malformed expression.") from None
        if len(stack) != 1:
            raise ValueError("Malformed expression.")
        return _number(stack[0]), exact and not context.flags[Inexact]


def _format(value: _Number, *, exact: bool) -> str:
    """Render a result after its `=` sign, or after `≈` when it is rounded."""
    if exact:
        return f"= {_format_exact(value)}"
    return f"≈ {_format_rounded(value)}"


def _format_exact(value: _Number) -> str:
    """Render a result without trailing zeros or a useless decimal part."""
    if isinstance(value, float):
        value = Decimal(repr(value))
    text = format(value, "f") if isinstance(value, Decimal) else str(value)
    return text.rstrip("0").rstrip(".") if "." in text else text


def _format_rounded(value: _Number) -> str:
    """Render a rounded result with its first significant digits only.

    Only those digits are right, so a very large or very small result is
    written in scientific notation instead of as a long, falsely exact number.
    """
    if value == 0:
        return "0"
    if isinstance(value, float):
        value = Decimal(repr(value))
    mantissa, exponent = f"{value:.{_SIGNIFICANT_DIGITS - 1}e}".split("e")
    if int(exponent) in _FIXED_EXPONENTS:
        return _format_exact(Decimal(f"{mantissa}e{exponent}"))
    return f"{mantissa.rstrip('0').rstrip('.')}e{exponent}"


async def _calculator(args: Mapping[str, Any]) -> str:
    expression = str(args.get("expression") or "").strip()
    if not expression:
        raise ValueError("The expression must not be empty.")

    # Restating the expression ties the result to the question for small models.
    value, exact = _evaluate(_to_postfix(expression))
    return f"{expression} {_format(value, exact=exact)}"
