"""Tests for application configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sensai.config import load_config
from sensai.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


def _write_schemas(path: Path) -> None:
    """Write the bundled schema fixtures beside a test configuration."""
    schemas = path.parent / "schemas"
    schemas.mkdir()
    for name in ("permission_decision", "plan"):
        (schemas / f"{name}.json").write_text('{"type":"object"}')


def test_structured_output_is_disabled_by_default(tmp_path: Path) -> None:
    """Existing configurations keep free-form model responses by default."""
    path = tmp_path / "sensai.toml"
    path.write_text('[ollama]\nurl = "http://ollama"\n')

    config = load_config(path)

    assert not config.structured_output.enabled


def test_structured_output_loads_all_agent_selected_schemas(tmp_path: Path) -> None:
    """The configuration loads each schema without selecting one itself."""
    path = tmp_path / "sensai.toml"
    path.write_text(
        '[ollama]\nurl = "http://ollama"\n\n[structured_output]\nenabled = true\n'
    )
    _write_schemas(path)

    config = load_config(path)

    assert config.structured_output.enabled
    assert config.structured_output.schemas == {
        "permission_decision": {"type": "object"},
        "plan": {"type": "object"},
    }


def test_config_schema_selection_is_rejected(tmp_path: Path) -> None:
    """The agent, rather than TOML, selects its output schema."""
    path = tmp_path / "sensai.toml"
    path.write_text('[structured_output]\nschema = "plan"\n')

    with pytest.raises(ConfigError, match="selected automatically"):
        load_config(path)
