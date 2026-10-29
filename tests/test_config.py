"""Tests for configuration parsing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sensai.config import McpServerConfig, load_config
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


def test_no_mcp_table_means_no_servers(tmp_path: Path) -> None:
    """Without an `[mcp]` table, no MCP server is configured."""
    assert load_config(_write(tmp_path, "")).mcp.servers == ()


def test_mcp_servers_are_parsed_with_tokens_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each `[mcp.servers.<name>]` table becomes a server, its token read from env."""
    monkeypatch.setenv("ALPHA_TOKEN", "s3cret")
    body = (
        '[mcp.servers.alpha]\nurl = "https://a.test/mcp"\ntoken_env = "ALPHA_TOKEN"\n'
        '[mcp.servers.beta]\nurl = "https://b.test/mcp"\n'
    )
    servers = load_config(_write(tmp_path, body)).mcp.servers
    assert servers == (
        McpServerConfig("alpha", "https://a.test/mcp", "ALPHA_TOKEN", "s3cret"),
        McpServerConfig("beta", "https://b.test/mcp"),
    )


@pytest.mark.parametrize("value", [None, ""])
def test_mcp_token_is_none_when_env_var_unset_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """A missing or empty `token_env` variable means no token."""
    if value is None:
        monkeypatch.delenv("ALPHA_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ALPHA_TOKEN", value)
    body = '[mcp.servers.alpha]\nurl = "https://a.test"\ntoken_env = "ALPHA_TOKEN"\n'
    assert load_config(_write(tmp_path, body)).mcp.servers[0].token is None


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[mcp]\nservers = 3\n", r"mcp\.servers must be a table"),
        ("[mcp.servers]\nalpha = 3\n", r"mcp\.servers\.alpha must be a table"),
        ("[mcp.servers.alpha]\n", r"mcp\.servers\.alpha\.url"),
        ("[mcp.servers.alpha]\nurl = 3\n", r"mcp\.servers\.alpha\.url"),
        (
            '[mcp.servers.alpha]\nurl = "u"\ntoken_env = 3\n',
            r"mcp\.servers\.alpha\.token_env",
        ),
        ('[mcp.servers.alpha]\nurl = "u"\nfoo = 1\n', "unknown key.*foo"),
        ('[mcp.servers.a__b]\nurl = "u"\n', "invalid server name"),
    ],
)
def test_invalid_mcp_servers_are_rejected(
    tmp_path: Path, body: str, message: str
) -> None:
    """Malformed MCP server tables raise a ConfigError naming the key."""
    with pytest.raises(ConfigError, match=message):
        load_config(_write(tmp_path, body))


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


def test_keep_alive_defaults_to_thirty_minutes(tmp_path: Path) -> None:
    """Without a value, the model stays loaded longer than Ollama's 5 minutes."""
    config = load_config(_write(tmp_path, '[ollama]\nurl = "http://o"\n'))

    assert config.ollama.keep_alive == "30m"


@pytest.mark.parametrize("value", ['"2h"', "-1", "600"])
def test_keep_alive_accepts_durations_and_seconds(tmp_path: Path, value: str) -> None:
    """A duration string or a number of seconds is passed on as written."""
    config = load_config(_write(tmp_path, f"[ollama]\nkeep_alive = {value}\n"))

    assert str(config.ollama.keep_alive) == value.strip('"')


@pytest.mark.parametrize("value", ["true", "1.5", "[1]"])
def test_invalid_keep_alive_is_rejected(tmp_path: Path, value: str) -> None:
    """Anything but a string or a whole number of seconds is refused."""
    with pytest.raises(ConfigError, match=r"ollama\.keep_alive"):
        load_config(_write(tmp_path, f"[ollama]\nkeep_alive = {value}\n"))
