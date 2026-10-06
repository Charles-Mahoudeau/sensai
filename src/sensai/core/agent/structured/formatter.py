"""Presentation formatting for validated structured agent output."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sensai.core.agent.structured.catalog import OutputSchemaName


def format_structured_output(name: OutputSchemaName, value: Any) -> str:
    """Render a validated structured response as Markdown for a front-end."""
    if not isinstance(value, dict):
        raise ValueError("structured response must be a JSON object")

    match name:
        case "plan":
            return _format_plan(value)
        case "permission_decision":
            return _format_permission_decision(value)


def _format_plan(value: dict[str, Any]) -> str:
    """Render a plan title and its ordered steps."""
    title = _string_field(value, "title")
    steps = value.get("steps")
    if not isinstance(steps, list):
        raise ValueError("plan response field 'steps' must be an array")

    lines = [f"## {title}"]
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError("plan steps must be JSON objects")
        step_title = _string_field(step, "title")
        description = _string_field(step, "description")
        priority = _string_field(step, "priority")
        lines.extend(
            [
                "",
                f"{index}. **{step_title}** ({priority} priority)",
                f"   {description}",
            ]
        )
    return "\n".join(lines)


def _format_permission_decision(value: dict[str, Any]) -> str:
    """Render a future human-in-the-loop permission request."""
    action = _string_field(value, "action")
    targets = value.get("targets")
    risk = _string_field(value, "risk")
    reason = _string_field(value, "reason")
    if not isinstance(targets, list) or not all(
        isinstance(target, str) for target in targets
    ):
        raise ValueError(
            "permission decision field 'targets' must be an array of strings"
        )

    target_list = ", ".join(targets)
    return (
        "## Confirmation required\n\n"
        f"**Action:** {action}\n\n"
        f"**Targets:** {target_list}\n\n"
        f"**Risk:** {risk}\n\n"
        f"{reason}"
    )


def _string_field(value: dict[str, Any], name: str) -> str:
    """Return a required string field from a validated response object."""
    field = value.get(name)
    if not isinstance(field, str):
        raise ValueError(f"structured response field {name!r} must be a string")
    return field
