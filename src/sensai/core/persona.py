"""Transform a persona into a system message."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensai.core.models.persona import Persona


def render_persona(persona: Persona) -> str:
    """Turn a persona into the text of a system message.

    Each section becomes a title, taken from its name (`response_scope` reads
    "Response scope"), followed by its entries. Sections keep their order, so
    a new one needs no code change.
    """
    lines: list[str] = []

    for section in persona.sections:
        if not section.entries:
            continue
        lines.append(f"{section.name.replace('_', ' ').capitalize()}:")
        lines.extend(f"- {entry.key}: {entry.value}" for entry in section.entries)

    return "\n".join(lines)
