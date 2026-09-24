"""Immutable models for tool specifications, calls, and results."""

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Mapping

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Represent one invocation of a tool."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict, hash=False)
    id: str | None = None

    def __post_init__(self) -> None:
        """Validate and freeze the tool arguments."""
        if not self.name:
            raise ValueError("ToolCall.name must not be empty")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Describe a tool exposed to the model."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}, hash=False
    )
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        """Validate the name and freeze the parameter schema."""
        if not _NAME_RE.match(self.name):
            raise ValueError(f"ToolSpec.name {self.name!r} must match [A-Za-z0-9_-]+")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Represent the result returned by a tool invocation."""

    name: str
    content: str
    call_id: str
    is_error: bool = False

    def __post_init__(self) -> None:
        """Validate the tool name."""
        if not _NAME_RE.match(self.name):
            raise ValueError(f"ToolResult.name {self.name!r} must match [A-Za-z0-9_-]+")

    @classmethod
    def error(cls, name: str, message: str, call_id: str) -> Self:
        """Build an error result for a tool invocation."""
        return cls(name, message, call_id, is_error=True)
