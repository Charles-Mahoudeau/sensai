"""Read personas from a directory of TOML files.

Each file is one persona, named after the file (`sensai.toml` is `sensei`).
Each TOML table is a section and each key in it is one entry::

    [identity]
    role = "A patient programming mentor"

    [response_scope]
    focus = "Software engineering questions"

Section names are free: any table is accepted and rendered in file order.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from sensai.core.models.persona import Persona, PersonaEntry, PersonaSection
from sensai.core.ports import PersonaInvalidError, PersonaNotFoundError


class TomlPersonaDir:
    """Implement the `PersonaSource` port over a directory of TOML files.

    The directory is read again on every call, so files added or edited while
    the app runs are picked up without a restart.
    """

    def __init__(self, path: Path) -> None:
        """Read personas from `path`; a missing directory holds no persona."""
        self._path = path

    def names(self) -> tuple[str, ...]:
        """Every persona file in the directory, sorted by name."""
        if not self._path.is_dir():
            return ()
        return tuple(sorted(p.stem for p in self._path.glob("*.toml") if p.is_file()))

    def load(self, name: str) -> Persona:
        """Read the current content of a persona file.

        Raises:
            PersonaNotFoundError: No file is called `<name>.toml`.
            PersonaInvalidError: The file is not valid TOML, holds a value
                outside a [section], or a value that is not a non-empty string.
        """
        path = self._path / f"{name}.toml"
        if not name or Path(name).name != name or not path.is_file():
            raise PersonaNotFoundError(f"Unknown persona {name!r}")
        try:
            with path.open("rb") as file:
                data = tomllib.load(file)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise PersonaInvalidError(f"{path}: invalid TOML: {error}") from None
        except OSError as error:
            raise PersonaInvalidError(f"{path}: cannot read: {error}") from None

        sections: list[PersonaSection] = []
        for section, entries in data.items():
            if not isinstance(entries, dict):
                raise PersonaInvalidError(f"{path}: {section!r} must be a [section]")
            for key, value in entries.items():
                if not key:
                    raise PersonaInvalidError(f"{path}: [{section}] has an empty key")
                if not isinstance(value, str) or not value:
                    raise PersonaInvalidError(
                        f"{path}: [{section}] {key} must be a non-empty string"
                    )
            sections.append(
                PersonaSection(
                    section,
                    tuple(PersonaEntry(key, value) for key, value in entries.items()),
                )
            )
        return Persona(name, tuple(sections))
