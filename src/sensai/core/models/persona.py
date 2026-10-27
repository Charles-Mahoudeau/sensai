"""Immutable models for the personas the agent can take on."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonaEntry:
    """One key-value line of a persona section."""

    key: str
    value: str

    def __post_init__(self) -> None:
        """Validate the key and the value."""
        if not self.key:
            raise ValueError("PersonaEntry.key must be a non-empty string")
        if not self.value:
            raise ValueError("PersonaEntry.value must be a non-empty string")


@dataclass(frozen=True, slots=True)
class PersonaSection:
    """A named group of entries, such as `identity` or `tone`.

    Sections are free-form: any name is allowed, so a persona can gain one
    without a code change.
    """

    name: str
    entries: tuple[PersonaEntry, ...]

    def __post_init__(self) -> None:
        """Validate the name."""
        if not self.name:
            raise ValueError("PersonaSection.name must be a non-empty string")


@dataclass(frozen=True, slots=True)
class Persona:
    """Who the agent acts as, injected into the system message.

    Attributes:
        name: What the user picks the persona by.
        sections: The persona's content, in the order it is rendered.
    """

    name: str
    sections: tuple[PersonaSection, ...]

    def __post_init__(self) -> None:
        """Validate the name."""
        if not self.name:
            raise ValueError("Persona.name must be a non-empty string")
