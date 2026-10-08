"""Immutable models for versioned prompts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """One saved version of a named prompt."""

    name: str
    version: int
    content: str
    created_at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        """Validate the fields that identify the version."""
        if not self.name:
            raise ValueError("PromptVersion.name must be a non-empty string")
        if self.version < 1:
            raise ValueError("PromptVersion.version must be at least 1")
