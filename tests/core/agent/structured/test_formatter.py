"""Tests for front-end formatting of validated structured output."""

from sensai.core.agent.structured import format_structured_output


def test_plan_is_rendered_as_markdown() -> None:
    """A validated plan becomes readable Markdown instead of raw JSON."""
    rendered = format_structured_output(
        "plan",
        {
            "title": "Release checklist",
            "steps": [
                {
                    "title": "Run tests",
                    "description": "Execute the test suite.",
                    "priority": "high",
                }
            ],
        },
    )

    assert rendered == (
        "## Release checklist\n\n"
        "1. **Run tests** (high priority)\n"
        "   Execute the test suite."
    )
