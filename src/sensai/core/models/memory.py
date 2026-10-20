"""Immutable models for stored sessions and long-term memory records."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

# The categories facts are filed under: English whatever the user's language,
# so that a search by category finds them.
MEMORY_CATEGORIES = ("preference", "identity", "project", "habit", "goal", "other")


def memory_search_terms(query: str) -> tuple[str, ...]:
    """Return distinct searchable words from a natural-language memory query."""
    return tuple(dict.fromkeys(re.findall(r"[^\W\d_]{3,}", query.lower())))


def fold_category(category: str) -> str:
    """Return a category without case or accents: `Préférence` is `preference`."""
    decomposed = unicodedata.normalize("NFKD", category.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


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


@dataclass(frozen=True, slots=True)
class UserProfile:
    """A key-value pair representing a user profile entry."""

    key: str
    value: str
    category: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Validate the fields that identify the record."""
        if not self.key:
            raise ValueError("UserProfile.key must be a non-empty string")
        if not self.value:
            raise ValueError("UserProfile.value must be a non-empty string")
