"""Immutable models for chat messages and model responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.models.tools import ToolCall

type Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class Message:
    """A message exchanged between a user, the model, and a tool."""

    role: Role
    tool_call_id: str | None = None
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_name: str | None = None
    reasoning_summary: str = ""

    def __post_init__(self) -> None:
        """Validate fields whose meaning depends on the message role."""
        if self.role not in (
            "system",
            "user",
            "assistant",
            "tool",
        ):
            raise ValueError(f"Invalid role {self.role!r}")
        if self.role == "tool" and not self.tool_name:
            raise ValueError("tool_name must be provided for role 'tool'")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool_call_id must be provided for role 'tool'")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages can carry tool_calls")
        if self.reasoning_summary and self.role != "assistant":
            raise ValueError("only assistant messages can have a reasoning_summary")
        if self.tool_name and self.role != "tool":
            raise ValueError("only tool messages can have a tool_name")

    @classmethod
    def system(cls, content: str) -> Message:
        """Build a system message."""
        return cls("system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        """Build a user message."""
        return cls("user", content=content)

    @classmethod
    def assistant(
        cls, content: str = "", tool_calls: tuple[ToolCall, ...] = ()
    ) -> Message:
        """Build an assistant message, optionally containing tool calls."""
        return cls("assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, content: str, tool_name: str, tool_call_id: str) -> Message:
        """Build a message containing a tool result."""
        return cls(
            "tool",
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ChatOptions:
    """Optional parameters controlling a model chat request."""

    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None
    response_schema: Mapping[str, Any] | None = field(default=None, hash=False)
    think: bool | None = None

    def __post_init__(self) -> None:
        """Freeze the response schema mapping."""
        if self.response_schema is not None:
            object.__setattr__(
                self, "response_schema", MappingProxyType(dict(self.response_schema))
            )


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage reported for a model response."""

    completion_tokens: int
    prompt_tokens: int

    def __post_init__(self) -> None:
        """Reject negative token counters."""
        if self.completion_tokens < 0:
            raise ValueError("completion_tokens must be non-negative")
        if self.prompt_tokens < 0:
            raise ValueError("prompt_tokens must be non-negative")

    @property
    def total_tokens(self) -> int:
        """Return the sum of prompt and completion tokens."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """Represent a tool call requested during model generation."""

    call: ToolCall
