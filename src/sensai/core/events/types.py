"""Event types published by the Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensai.core.errors import SensaiError
    from sensai.core.models.llm import Message


@dataclass(frozen=True, slots=True)
class MessageStarted:
    """Event indicating that a message has started processing."""

    submission_id: str


@dataclass(frozen=True, slots=True)
class TokenGenerated:
    """Event indicating that a token has been generated for a message."""

    submission_id: str
    text: str


@dataclass(frozen=True, slots=True)
class MessageCompleted:
    """Event indicating that a message has been fully processed."""

    submission_id: str
    message: Message


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Event indicating that an error occurred during message processing."""

    submission_id: str
    error: SensaiError


@dataclass(frozen=True, slots=True)
class Done:
    """Event indicating that message processing is done."""

    submission_id: str


type Event = MessageStarted | TokenGenerated | MessageCompleted | ErrorEvent | Done
