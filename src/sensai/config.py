"""Configuration parsing."""

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sensai.core.models import SOURCE_SEPARATOR, ThinkingEffort
from sensai.exceptions import ConfigError

SUPPORTED_STRUCTURED_OUTPUT_SCHEMAS = frozenset({"permission_decision", "plan"})
DEFAULT_KEEP_ALIVE = "30m"


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for Ollama.

    Attributes:
        url: The Ollama server URL.
        keep_alive: How long Ollama keeps the model loaded after a request: a
            duration such as `"30m"`, or seconds (`-1` keeps it until Ollama
            stops). Ollama's own default is 5 minutes.
    """

    url: str
    keep_alive: str | int = DEFAULT_KEEP_ALIVE


@dataclass(frozen=True)
class ProfileConfig:
    """Configuration for a user profile."""

    profile: Path


@dataclass(frozen=True)
class PersonasConfig:
    """Configuration for the personas the agent can take on.

    Attributes:
        path: The directory holding one TOML file per persona.
        default: The persona the chat starts with; the base prompt when None.
    """

    path: Path = Path("config/personas")
    default: str | None = None


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
class McpServerConfig:
    """Configuration for one HTTP MCP server.

    Attributes:
        name: The server name, used as its tool namespace prefix.
        url: The server endpoint.
        token_env: The environment variable holding the bearer token, if any.
        token: The bearer token read from `token_env`; None when unset or empty.
    """

    name: str
    url: str
    token_env: str | None = None
    token: str | None = None


@dataclass(frozen=True)
class McpConfig:
    """Configuration for MCP servers.

    Secrets come from the environment, never from the TOML file.
    """

    servers: tuple[McpServerConfig, ...] = ()


@dataclass(frozen=True)
class SandboxConfig:
    """Configuration for the sandbox where the model's Python code runs.

    Attributes:
        enabled: Whether `run_python` is offered (it also needs Docker).
        image: The Docker image runs use.
        timeout: Seconds a run may last.
        memory: The memory a run may use, in Docker's notation ("512m").
        cpus: How many CPUs a run may use.
        artifacts_dir: Where the files runs create are saved.
    """

    enabled: bool = False
    image: str = "sensai-sandbox"
    timeout: float = 30.0
    memory: str = "512m"
    cpus: float = 1.0
    artifacts_dir: Path = Path("artifacts")


@dataclass(frozen=True)
class Config:
    """Global application configuration."""

    model: str
    ollama: OllamaConfig
    user_profile: ProfileConfig
    personas: PersonasConfig = PersonasConfig()
    agent: AgentConfig = AgentConfig()
    structured_output: StructuredOutputConfig = field(
        default_factory=StructuredOutputConfig
    )
    mcp: McpConfig = McpConfig()
    sandbox: SandboxConfig = SandboxConfig()


def _parse_sandbox(data: dict[str, Any], base: Path) -> SandboxConfig:
    defaults = SandboxConfig()
    try:
        config = SandboxConfig(
            enabled=bool(data.get("enabled", defaults.enabled)),
            image=str(data.get("image", defaults.image)),
            timeout=float(data.get("timeout", defaults.timeout)),
            memory=str(data.get("memory", defaults.memory)),
            cpus=float(data.get("cpus", defaults.cpus)),
            artifacts_dir=base / str(data.get("artifacts_dir", defaults.artifacts_dir)),
        )
    except (TypeError, ValueError) as error:
        raise ConfigError(f"invalid [sandbox] value: {error}") from None
    if config.timeout <= 0 or config.cpus <= 0:
        raise ConfigError("sandbox.timeout and sandbox.cpus must be positive")
    return config


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


def _parse_keep_alive(value: object) -> str | int:
    # bool is an int in Python, but `keep_alive = true` means nothing to Ollama
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise ConfigError(
            f"ollama.keep_alive must be a duration like '30m' or a number of "
            f"seconds, got {type(value).__name__} {value!r}"
        )
    return value


def _parse_mcp_servers(value: object) -> tuple[McpServerConfig, ...]:
    if not isinstance(value, dict):
        raise ConfigError("mcp.servers must be a table of server tables")
    servers: list[McpServerConfig] = []
    for name, entry in value.items():
        key = f"mcp.servers.{name}"
        if not name or SOURCE_SEPARATOR in name:
            raise ConfigError(
                f"invalid server name {name!r} in mcp.servers, it must be non-empty "
                f"and must not contain {SOURCE_SEPARATOR!r}"
            )
        if not isinstance(entry, dict):
            raise ConfigError(f"{key} must be a table")
        if unknown := sorted(entry.keys() - {"url", "token_env"}):
            raise ConfigError(f"unknown key(s) in {key}: {', '.join(unknown)}")
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            raise ConfigError(f"{key}.url must be a non-empty string")
        token_env = entry.get("token_env")
        if token_env is not None and (not isinstance(token_env, str) or not token_env):
            raise ConfigError(f"{key}.token_env must be a non-empty string")
        token = os.environ.get(token_env) or None if token_env else None
        servers.append(McpServerConfig(name, url, token_env, token))
    return tuple(servers)


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

    personas = data.get("personas", {})
    default_persona = personas.get("default")
    if default_persona is not None and (
        not isinstance(default_persona, str) or not default_persona
    ):
        raise ConfigError("personas.default must be a non-empty string")

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
        ollama=OllamaConfig(
            url=data.get("ollama", {}).get("url", ""),
            keep_alive=_parse_keep_alive(
                data.get("ollama", {}).get("keep_alive", DEFAULT_KEEP_ALIVE)
            ),
        ),
        user_profile=ProfileConfig(
            profile=base / Path(data.get("profile", {}).get("path", "profile.toml"))
        ),
        personas=PersonasConfig(
            path=base / Path(personas.get("path", "config/personas")),
            default=default_persona,
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
        mcp=McpConfig(
            servers=_parse_mcp_servers(data.get("mcp", {}).get("servers", {}))
        ),
        sandbox=_parse_sandbox(data.get("sandbox", {}), base),
    )

    return config
