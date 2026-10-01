"""Configuration parsing."""

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from pathlib import Path

from sensai.exceptions import ConfigError

if TYPE_CHECKING:
    import pathlib


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for Ollama."""

    url: str


@dataclass(frozen=True)
class StorageConfig:
    """Configuration for storage."""

    database: Path


@dataclass(frozen=True)
class ProfileConfig:
    """Configuration for a user profile."""

    profile: Path


@dataclass(frozen=True)
class Config:
    """Global application configuration."""

    model: str
    ollama: OllamaConfig
    db: StorageConfig
    user_profile: ProfileConfig


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

    config = Config(
        model=data.get("model", ""),
        ollama=OllamaConfig(url=data.get("ollama", {}).get("url", "")),
        db=StorageConfig(
            database=Path(data.get("storage", {}).get("database", "database.db"))
        ),
        user_profile=ProfileConfig(
            profile=Path(data.get("profile", {}).get("profile", "profile.toml"))
        ),
    )

    return config
