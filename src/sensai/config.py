"""Configuration parsing."""

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sensai.core.models import ThinkingEffort
from sensai.exceptions import ConfigError

SUPPORTED_STRUCTURED_OUTPUT_SCHEMAS = frozenset({"permission_decision", "plan"})


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
class StructuredOutputConfig:
    """Configuration for schema-constrained model responses."""

    enabled: bool = False
    schemas: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class McpConfig:
    """Configuration for MCP servers.

    Secrets come from the environment, never from the TOML file.
    """

    github_token: str | None = None


@dataclass(frozen=True)
class Config:
    """Global application configuration."""

    model: str
    ollama: OllamaConfig
    user_profile: ProfileConfig
    agent: AgentConfig = AgentConfig()
    structured_output: StructuredOutputConfig = field(
        default_factory=StructuredOutputConfig
    )
    mcp: McpConfig = McpConfig()


def _parse_thinking_effort(value: object) -> ThinkingEffort:
    choices = ", ".join(effort.name.lower() for effort in ThinkingEffort)
    if not isinstance(value, str):
        raise ConfigError(
            f"agent.thinking_effort must be a string, got {type(value).__name__} "
            f"{value!r}, expected one of: {choices}"
        )
    try:
        return ThinkingEffort[value.upper()]
    except KeyError:
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

    structured_output = data.get("structured_output", {})
    if "schema" in structured_output:
        raise ConfigError(
            "structured output schemas are selected automatically by the agent"
        )

    schemas: dict[str, dict[str, Any]] = {}
    if structured_output.get("enabled", False):
        for schema_name in SUPPORTED_STRUCTURED_OUTPUT_SCHEMAS:
            schema_path = path.parent / "schemas" / f"{schema_name}.json"
            try:
                schema = json.loads(schema_path.read_text())
            except FileNotFoundError:
                raise ConfigError(
                    f"structured output schema not found at {schema_path}"
                ) from None
            except json.JSONDecodeError as error:
                raise ConfigError(
                    f"invalid JSON in structured output schema {schema_path}: {error}"
                ) from error
            if not isinstance(schema, dict):
                raise ConfigError("structured output schema must be a JSON object")
            schemas[schema_name] = schema

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
        structured_output=StructuredOutputConfig(
            enabled=structured_output.get("enabled", False),
            schemas=schemas,
        ),
        mcp=McpConfig(github_token=os.environ.get("GITHUB_TOKEN") or None),
    )

    return config
