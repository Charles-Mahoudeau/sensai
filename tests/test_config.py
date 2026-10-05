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
