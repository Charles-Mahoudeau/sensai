"""The active persona shown next to the thinking effort."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from sensai.core.models.persona import Persona


class PersonaLabel(Static):
    """The name of the active persona, hidden when there is none."""

    DEFAULT_CSS = """
    PersonaLabel {
        width: auto;
        padding: 0 3 0 0;
        color: $text-muted;
    }
    """

    def __init__(self, persona: Persona | None) -> None:
        """Show the given persona."""
        super().__init__(id="persona", markup=False)
        self.persona_name: str | None = None
        self.set_persona(persona)

    def set_persona(self, persona: Persona | None) -> None:
        """Show another persona, or hide the label without one."""
        self.persona_name = persona.name if persona is not None else None
        self.display = self.persona_name is not None
        self.update(self.persona_name or "")
