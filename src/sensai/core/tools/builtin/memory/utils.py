"""Argument validation and result serialization for memory tools."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sensai.core.models.memory import memory_search_terms

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models.memory import MemoryRecord
    from sensai.core.ports import MemoryRepository

# Share of name words in common above which two records are the same subject.
_SAME_SUBJECT = 0.6


async def find_similar(memory: MemoryRepository, name: str) -> MemoryRecord | None:
    """Return a stored record whose name is about the same subject, if any."""
    terms = set(memory_search_terms(name))
    if not terms:
        return None
    for record in await memory.find(query=name):
        other = set(memory_search_terms(record.name))
        if other and len(terms & other) / min(len(terms), len(other)) >= _SAME_SUBJECT:
            return record
    return None


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


def reject_unknown(arguments: Mapping[str, Any], allowed: frozenset[str]) -> None:
    """Raise when the model sent an argument the tool does not have.

    Ignoring it would silently drop the data it carried.
    """
    if unknown := sorted(set(arguments) - allowed):
        raise ValueError(
            f"unexpected argument(s): {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(allowed))}"
        )


def integer_argument(value: Any) -> int | None:
    """Return `value` as an int, accepting digit strings such as `"5"`.

    Small models often send numbers as strings; anything else returns None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        return int(value)
    return None


def memory_id(arguments: Mapping[str, Any]) -> int:
    """Return a required positive memory identifier."""
    value = integer_argument(arguments.get("memory_id"))
    if value is None or value < 1:
        raise ValueError("memory_id must be a positive integer")
    return value


def record_json(record: MemoryRecord) -> str:
    """Serialize one memory record for a model tool result.

    Accents are kept as they are: escaped, a French word is unreadable for a
    small model.
    """
    return json.dumps(record_data(record), sort_keys=True, ensure_ascii=False)


def records_json(records: Sequence[MemoryRecord]) -> str:
    """Serialize a memory search result for a model tool result."""
    return json.dumps(
        {"records": [record_data(record) for record in records]},
        sort_keys=True,
        ensure_ascii=False,
    )


def record_data(record: MemoryRecord) -> dict[str, int | str | None]:
    """Convert a memory record into JSON-compatible tool-result data."""
    return {
        "id": record.id,
        "name": record.name,
        "type": record.type,
        "description": record.description,
    }
