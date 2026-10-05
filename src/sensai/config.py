"""Configuration parsing."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sensai.core.models import ThinkingEffort
from sensai.exceptions import ConfigError


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for Ollama."""

    url: str


@dataclass(frozen=True)
class ProfileConfig:
    """Configuration for a user profile."""

    profile: Path


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for the agent."""

    thinking_effort: ThinkingEffort = ThinkingEffort.MEDIUM


@dataclass(frozen=True)
class Config:
    """Global application configuration."""

    model: str
    ollama: OllamaConfig
    user_profile: ProfileConfig
    agent: AgentConfig = AgentConfig()


def _parse_thinking_effort(value: str) -> ThinkingEffort:
    try:
        return ThinkingEffort[value.upper()]
    except KeyError:
        choices = ", ".join(effort.name.lower() for effort in ThinkingEffort)
        raise ConfigError(
            f"invalid agent.thinking_effort {value!r}, expected one of: {choices}"
        ) from None


def load_config(path: Path, overrides: dict[str, Any] | None = None) -> Config:
    """Loads the configuration from the given path and overrides.

    Args:
        path: The path to the configuration file.
        overrides: Optional overrides for the configuration.

    Returns:
        The loaded configuration.

    Raises:
        ConfigError: If the configuration file is not found or cannot be loaded.
    """
    data: dict[str, Any] = {}

    if path is not None:
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            raise ConfigError(f"config file not found at {path}") from None
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"failed to load config from {path}: {e}") from None

    data |= {k: v for k, v in (overrides or {}).items() if v is not None}
    base = path.parent.parent

    config = Config(
        model=data.get("model", ""),
        ollama=OllamaConfig(url=data.get("ollama", {}).get("url", "")),
        user_profile=ProfileConfig(
            profile=base / Path(data.get("profile", {}).get("path", "profile.toml"))
        ),
        agent=AgentConfig(
            thinking_effort=_parse_thinking_effort(
                data.get("agent", {}).get("thinking_effort", "medium")
            )
        ),
    )

    return config
