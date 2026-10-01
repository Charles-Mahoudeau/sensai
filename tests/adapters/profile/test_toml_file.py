"""Tests for reading the user profile from a TOML file."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sensai.adapters.profile import ProfileFileError, read_profile_file

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "profile.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_entries_grouped_by_category(tmp_path: Path) -> None:
    """Each section becomes a category holding its key/value pairs."""
    path = _write(
        tmp_path,
        '[identity]\nname = "Tristan"\n\n'
        '[preference]\nlanguage = "Python"\n\n'
        '[instruction]\nstyle = "Answer concisely"\n',
    )

    assert read_profile_file(path) == {
        "identity": {"name": "Tristan"},
        "preference": {"language": "Python"},
        "instruction": {"style": "Answer concisely"},
    }


def test_missing_file_is_an_empty_profile(tmp_path: Path) -> None:
    """No profile file is normal: the profile is just empty."""
    assert read_profile_file(tmp_path / "does-not-exist.toml") == {}


def test_empty_file_is_an_empty_profile(tmp_path: Path) -> None:
    """An empty file gives an empty profile."""
    assert read_profile_file(_write(tmp_path, "")) == {}


def test_rejects_unknown_category(tmp_path: Path) -> None:
    """A section outside the allowed categories is refused."""
    path = _write(tmp_path, '[hobbies]\nsport = "climbing"\n')

    with pytest.raises(ProfileFileError, match="hobbies"):
        read_profile_file(path)


@pytest.mark.parametrize(
    "line",
    ["age = 22", "likes = true", 'tags = ["a", "b"]', 'name = ""'],
)
def test_rejects_value_that_is_not_a_non_empty_string(
    tmp_path: Path, line: str
) -> None:
    """Numbers, booleans, lists and empty strings are refused."""
    path = _write(tmp_path, f"[identity]\n{line}\n")

    with pytest.raises(ProfileFileError, match="non-empty string"):
        read_profile_file(path)


def test_rejects_top_level_key_outside_a_section(tmp_path: Path) -> None:
    """A key must live inside a [category] section."""
    path = _write(tmp_path, 'name = "Tristan"\n')

    with pytest.raises(ProfileFileError):
        read_profile_file(path)


def test_rejects_invalid_toml(tmp_path: Path) -> None:
    """A syntax error is reported as a ProfileFileError."""
    path = _write(tmp_path, "[identity\nname = \n")

    with pytest.raises(ProfileFileError, match="invalid TOML"):
        read_profile_file(path)
