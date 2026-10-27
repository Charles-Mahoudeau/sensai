"""Tests for reading personas from a directory of TOML files."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sensai.adapters.persona import TomlPersonaDir
from sensai.core.models.persona import Persona, PersonaEntry, PersonaSection
from sensai.core.ports import PersonaInvalidError, PersonaNotFoundError

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / f"{name}.toml").write_text(text, encoding="utf-8")


def test_names_lists_the_toml_files_sorted(tmp_path: Path) -> None:
    """Each .toml file is a persona; other files and directories are not."""
    _write(tmp_path, "sensei", "")
    _write(tmp_path, "pirate", "")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / "dir.toml").mkdir()

    assert TomlPersonaDir(tmp_path).names() == ("pirate", "sensei")


def test_missing_directory_has_no_persona(tmp_path: Path) -> None:
    """No persona directory is normal: there is just nothing to pick."""
    assert TomlPersonaDir(tmp_path / "missing").names() == ()


def test_load_reads_any_section_in_file_order(tmp_path: Path) -> None:
    """Section names are free and keep the order of the file."""
    _write(
        tmp_path,
        "sensei",
        '[tone]\nstyle = "calm"\n\n'
        '[examples]\ngreeting = "Hello, student"\nfarewell = "Keep practicing"\n',
    )

    assert TomlPersonaDir(tmp_path).load("sensei") == Persona(
        "sensei",
        (
            PersonaSection("tone", (PersonaEntry("style", "calm"),)),
            PersonaSection(
                "examples",
                (
                    PersonaEntry("greeting", "Hello, student"),
                    PersonaEntry("farewell", "Keep practicing"),
                ),
            ),
        ),
    )


def test_files_are_read_again_on_every_call(tmp_path: Path) -> None:
    """Personas added or edited after creation are picked up."""
    personas = TomlPersonaDir(tmp_path)
    _write(tmp_path, "sensei", '[tone]\nstyle = "calm"\n')
    assert personas.names() == ("sensei",)

    _write(tmp_path, "sensei", '[tone]\nstyle = "strict"\n')

    assert personas.load("sensei").sections[0].entries == (
        PersonaEntry("style", "strict"),
    )


@pytest.mark.parametrize("name", ["ghost", "", "../outside", "sub/inside"])
def test_load_rejects_unknown_names(tmp_path: Path, name: str) -> None:
    """Only a file directly in the directory is a persona."""
    directory = tmp_path / "personas"
    (directory / "sub").mkdir(parents=True)
    _write(tmp_path, "outside", "")
    _write(directory / "sub", "inside", "")

    with pytest.raises(PersonaNotFoundError):
        TomlPersonaDir(directory).load(name)


def test_rejects_invalid_toml(tmp_path: Path) -> None:
    """A file that is not TOML is reported, not skipped."""
    _write(tmp_path, "sensei", "not = [valid")

    with pytest.raises(PersonaInvalidError, match="invalid TOML"):
        TomlPersonaDir(tmp_path).load("sensei")


def test_rejects_a_value_outside_a_section(tmp_path: Path) -> None:
    """Every entry must belong to a [section]."""
    _write(tmp_path, "sensei", 'role = "mentor"\n')

    with pytest.raises(PersonaInvalidError, match="must be a"):
        TomlPersonaDir(tmp_path).load("sensei")


@pytest.mark.parametrize("value", ['""', "3", "true"])
def test_rejects_values_that_are_not_text(tmp_path: Path, value: str) -> None:
    """A value must be a non-empty string."""
    _write(tmp_path, "sensei", f"[tone]\nstyle = {value}\n")

    with pytest.raises(PersonaInvalidError, match="non-empty string"):
        TomlPersonaDir(tmp_path).load("sensei")
