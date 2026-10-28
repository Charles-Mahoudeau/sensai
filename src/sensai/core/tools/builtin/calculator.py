"""Calculator tool evaluating arithmetic expressions."""

from typing import TYPE_CHECKING, Any

from mathparse import mathparse

from sensai.core.models import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.tools.registry import ToolRegistry


def register_self(tool_registry: ToolRegistry) -> None:
    """Registers the calculator tool into a tool registry."""
    tool_registry.register(
        ToolSpec(
            name="calculator",
            description=(
                "Evaluates an arithmetic expression and returns the exact result. "
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


async def _calculator(args: Mapping[str, Any]) -> str:
    expression = str(args.get("expression") or "").strip()
    if not expression:
        raise ValueError("The expression must not be empty.")

    postfix = _to_postfix(expression)
    return str(mathparse.evaluate_postfix(postfix))
