"""Tests for configuration parsing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sensai.config import load_config
from sensai.core.models import ThinkingEffort
from sensai.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config" / "sensai.toml"
    path.parent.mkdir()
    path.write_text(body)
    return path


def test_thinking_effort_defaults_to_medium(tmp_path: Path) -> None:
    """Without an `[agent]` table the effort is medium."""
    config = load_config(_write(tmp_path, ""))

    assert config.agent.thinking_effort is ThinkingEffort.MEDIUM


def test_thinking_effort_is_read_case_insensitively(tmp_path: Path) -> None:
    """The configured effort name selects the enum member."""
    config = load_config(_write(tmp_path, '[agent]\nthinking_effort = "Ultra"\n'))

    assert config.agent.thinking_effort is ThinkingEffort.ULTRA


def test_unknown_thinking_effort_is_rejected(tmp_path: Path) -> None:
    """An unknown effort name raises a ConfigError listing the choices."""
    with pytest.raises(ConfigError, match="expected one of: none, low"):
        load_config(_write(tmp_path, '[agent]\nthinking_effort = "max"\n'))


def test_non_string_thinking_effort_is_rejected(tmp_path: Path) -> None:
    """A non-string effort raises a ConfigError listing the choices."""
    with pytest.raises(ConfigError, match=r"must be a string.*expected one of: none"):
        load_config(_write(tmp_path, "[agent]\nthinking_effort = 3\n"))


def test_github_token_is_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GITHUB_TOKEN` fills `mcp.github_token`."""
    monkeypatch.setenv("GITHUB_TOKEN", "s3cret")
    assert load_config(_write(tmp_path, "")).mcp.github_token == "s3cret"


@pytest.mark.parametrize("value", [None, ""])
def test_github_token_is_none_when_unset_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """A missing or empty `GITHUB_TOKEN` means no token."""
    if value is None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    else:
        monkeypatch.setenv("GITHUB_TOKEN", value)
    assert load_config(_write(tmp_path, "")).mcp.github_token is None


def test_personas_default_to_the_config_directory(tmp_path: Path) -> None:
    """Without a `[personas]` table they live in config/personas, none active."""
    config = load_config(_write(tmp_path, ""))

    assert config.personas.path == tmp_path / "config" / "personas"
    assert config.personas.default is None


def test_personas_are_read_from_the_file(tmp_path: Path) -> None:
    """The directory is relative to the project and the default is kept."""
    config = load_config(
        _write(tmp_path, '[personas]\npath = "my/personas"\ndefault = "sensei"\n')
    )

    assert config.personas.path == tmp_path / "my" / "personas"
    assert config.personas.default == "sensei"


@pytest.mark.parametrize("value", ['""', "3"])
def test_invalid_default_persona_is_rejected(tmp_path: Path, value: str) -> None:
    """The default persona must be a non-empty name."""
    with pytest.raises(ConfigError, match=r"personas\.default"):
        load_config(_write(tmp_path, f"[personas]\ndefault = {value}\n"))
