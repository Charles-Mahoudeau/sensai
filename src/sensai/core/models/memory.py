"""Immutable models for stored sessions and long-term memory records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class Session:
    """A saved conversation."""

    id: int
    model: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None

    def __post_init__(self) -> None:
        """Validate the model name."""
        if not self.model:
            raise ValueError("Session.model must be a non-empty string")


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """A long-term memory entry that the agent can create, read and update."""

    id: int
    name: str
    type: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None

    def __post_init__(self) -> None:
        """Validate the fields that identify the record."""
        if not self.name:
            raise ValueError("MemoryRecord.name must be a non-empty string")
        if not self.type:
            raise ValueError("MemoryRecord.type must be a non-empty string")
