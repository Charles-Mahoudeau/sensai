"""Read the user profile from a TOML file.

Each TOML table is a category and each key in it is one profile entry::

    [identity]
    name = "Tristan"

    [instruction]
    style = "Answer concisely"
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from pathlib import Path

# Must match the CHECK constraint on the `category` column of the profile table.
PROFILE_CATEGORIES = frozenset({"identity", "preference", "instruction", "other"})


class ProfileFileError(SensaiError):
    """The profile file exists but is not valid."""


def read_profile_file(path: Path) -> dict[str, dict[str, str]]:
    """Return the profile as `{category: {key: value}}`.

    Args:
        path: The profile file. A missing file means an empty profile.

    Returns:
        The entries grouped by category; empty if the file does not exist.

    Raises:
        ProfileFileError: The file is not valid TOML, uses an unknown
            category, or holds a value that is not a non-empty string.
    """
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as error:
        raise ProfileFileError(f"{path}: invalid TOML: {error}") from None

    profile: dict[str, dict[str, str]] = {}
    for category, entries in data.items():
        if category not in PROFILE_CATEGORIES:
            allowed = ", ".join(sorted(PROFILE_CATEGORIES))
            raise ProfileFileError(
                f"{path}: unknown section [{category}] (allowed: {allowed})"
            )
        if not isinstance(entries, dict):
            raise ProfileFileError(f"{path}: {category!r} must be a [section]")
        profile[category] = {}
        for key, value in entries.items():
            if not isinstance(value, str) or not value:
                raise ProfileFileError(
                    f"{path}: [{category}] {key} must be a non-empty string"
                )
            profile[category][key] = value
    return profile
