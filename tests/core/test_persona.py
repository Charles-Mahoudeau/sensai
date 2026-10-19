"""Tests for rendering a persona into a system message."""

from __future__ import annotations

from sensai.core.models.persona import Persona, PersonaEntry, PersonaSection
from sensai.core.persona import render_persona


def test_renders_every_section_in_order() -> None:
    """Sections keep their order and their names become titles."""
    persona = Persona(
        "sensei",
        (
            PersonaSection("tone", (PersonaEntry("style", "calm"),)),
            PersonaSection(
                "response_scope",
                (PersonaEntry("focus", "code"), PersonaEntry("length", "short")),
            ),
        ),
    )

    assert render_persona(persona) == (
        "Tone:\n- style: calm\nResponse scope:\n- focus: code\n- length: short"
    )


def test_skips_empty_sections() -> None:
    """A section with no entry adds no title."""
    persona = Persona(
        "sensei",
        (
            PersonaSection("identity", ()),
            PersonaSection("tone", (PersonaEntry("style", "calm"),)),
        ),
    )

    assert render_persona(persona) == "Tone:\n- style: calm"


def test_empty_persona_renders_nothing() -> None:
    """A persona with no section adds nothing to the system message."""
    assert render_persona(Persona("blank", ())) == ""
