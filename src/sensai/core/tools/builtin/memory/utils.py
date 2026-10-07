"""Argument validation and result serialization for memory tools."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models.memory import MemoryRecord


def required_string(arguments: Mapping[str, Any], field: str) -> str:
    """Return a required non-empty string argument."""
    value = arguments.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def optional_string(arguments: Mapping[str, Any], field: str) -> str | None:
    """Return an optional string argument, preserving an empty string."""
    value = arguments.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def memory_id(arguments: Mapping[str, Any]) -> int:
    """Return a required positive memory identifier."""
    value = arguments.get("memory_id")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("memory_id must be a positive integer")
    return value


def record_json(record: MemoryRecord) -> str:
    """Serialize one memory record for a model tool result."""
    return json.dumps(record_data(record), sort_keys=True)


def records_json(records: Sequence[MemoryRecord]) -> str:
    """Serialize a memory search result for a model tool result."""
    return json.dumps(
        {"records": [record_data(record) for record in records]}, sort_keys=True
    )


def record_data(record: MemoryRecord) -> dict[str, int | str | None]:
    """Convert a memory record into JSON-compatible tool-result data."""
    return {
        "id": record.id,
        "name": record.name,
        "type": record.type,
        "description": record.description,
    }
