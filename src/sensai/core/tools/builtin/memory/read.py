"""Tool for retrieving persistent memory records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolSpec
from sensai.core.tools.builtin.memory.utils import (
    memory_id,
    record_json,
    records_json,
    required_string,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolHandler


_DEFAULT_LIMIT = 5
_MAX_LIMIT = 10


def spec() -> ToolSpec:
    """Describe retrieval of one or more memory records."""
    return ToolSpec(
        name="memory_read",
        description=(
            "Retrieves a memory by id, or searches memories by category and "
            "keywords. Always provide an id, category, or focused keyword. "
            "Use it before creating or updating a memory."
        ),
        parameters={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer", "minimum": 1},
                "type": {"type": "string", "description": "Category filter."},
                "query": {"type": "string", "description": "Text search query."},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_LIMIT,
                    "default": _DEFAULT_LIMIT,
                    "description": "Maximum records to return.",
                },
            },
            "anyOf": [
                {"required": ["memory_id"]},
                {"required": ["type"]},
                {"required": ["query"]},
            ],
            "additionalProperties": False,
        },
        requires_confirmation=False,
    )


def handler(memory: MemoryRepository) -> ToolHandler:
    """Build the registry handler for memory retrieval."""

    async def read(arguments: Mapping[str, Any]) -> str:
        if "memory_id" in arguments:
            return record_json(await memory.get(memory_id(arguments)))
        if "type" not in arguments and "query" not in arguments:
            raise ValueError("memory_read requires memory_id, type, or query")
        records = await memory.find(
            type=_filter(arguments, "type"),
            query=_filter(arguments, "query"),
        )
        return records_json(records[: _limit(arguments)])

    return read


def _filter(arguments: Mapping[str, Any], field: str) -> str | None:
    """Return a non-empty filter only when the caller supplied one."""
    if field not in arguments:
        return None
    return required_string(arguments, field)


def _limit(arguments: Mapping[str, Any]) -> int:
    """Return a bounded result limit for a memory search."""
    value = arguments.get("limit", _DEFAULT_LIMIT)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("limit must be an integer")
    if not 1 <= value <= _MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
    return value
