"""Tests for front-end formatting of validated structured output."""

from sensai.core.agent.structured import format_structured_output


def test_plan_is_rendered_as_markdown() -> None:
    """A validated plan becomes readable Markdown instead of raw JSON."""
    rendered = format_structured_output(
        "plan",
        {
            "title": "Solve x² - 5x + 6 = 0",
            "steps": [
                {
                    "title": "Compute the discriminant",
                    "description": "Read a, b and c, then compute it.",
                    "notion": "Δ = b² - 4ac",
                }
            ],
            "check": "Put each solution back into the equation.",
        },
    )

    assert rendered == (
        "## Solve x² - 5x + 6 = 0\n\n"
        "1. **Compute the discriminant**\n"
        "   Read a, b and c, then compute it.\n"
        "   *Δ = b² - 4ac*\n\n"
        "**✓** Put each solution back into the equation."
    )
