"""Transform the user profile into a system message."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.memory import UserProfile

_TITLES = {
    "identity": "About the user",
    "preference": "User preferences",
    "instruction": "Instructions to follow",
    "other": "Other notes",
}


def render_profile(entries: Sequence[UserProfile]) -> str:
    """Turn the profile entries into the text of a system message."""
    lines: list[str] = []

    for category, title in _TITLES.items():
        in_category = [e for e in entries if e.category == category]
        if not in_category:
            continue
        lines.append(f"{title}:")
        for entry in in_category:
            lines.extend([f"- {entry.key}: {entry.value}"])

    return "\n".join(lines)
