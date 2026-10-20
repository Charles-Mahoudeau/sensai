"""Fake implementing the persona source port."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.core.ports import PersonaNotFoundError

if TYPE_CHECKING:
    from sensai.core.models.persona import Persona


class InMemoryPersonaSource:
    """Keep personas in a dict; tests add or replace them through `personas`.

    Implements the `PersonaSource` port.
    """

    def __init__(self, *personas: Persona) -> None:
        """Start with the given personas, keyed by name."""
        self.personas = {persona.name: persona for persona in personas}

    def names(self) -> tuple[str, ...]:
        """Every persona, sorted by name."""
        return tuple(sorted(self.personas))

    def load(self, name: str) -> Persona:
        """Return the persona called `name`."""
        try:
            return self.personas[name]
        except KeyError:
            raise PersonaNotFoundError(f"Unknown persona {name!r}") from None
