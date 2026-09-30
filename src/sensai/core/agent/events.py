"""Agent events."""

from dataclasses import dataclass

from sensai.core.models import TextDelta, ToolCall, ToolResult
from sensai.core.models.llm import Message, ThinkingDelta


@dataclass(frozen=True, slots=True)
class ToolRunStarted:
    """Event emitted when a tool run is started."""

    call: ToolCall


@dataclass(frozen=True, slots=True)
class ToolRunFinished:
    """Event emitted when a tool run is finished."""

    call: ToolCall
    result: ToolResult


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    """Event emitted when a turn is completed."""

    messages: list[Message]  # the list of produced messages this turn


AgentEvent = (
    TextDelta | ThinkingDelta | ToolRunStarted | ToolRunFinished | TurnCompleted
)
