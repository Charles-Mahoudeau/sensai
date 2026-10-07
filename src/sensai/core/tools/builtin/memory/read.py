"""Tool for retrieving persistent memory records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolSpec
from sensai.core.tools.builtin.memory.utils import (
    memory_id,
    optional_string,
    record_json,
    records_json,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolHandler


def spec() -> ToolSpec:
    """Describe retrieval of one or more memory records."""
    return ToolSpec(
        name="memory_read",
        description=(
            "Retrieves a memory by id, or searches memories by category and "
            "keywords. Use it before creating or updating a memory."
        ),
        parameters={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer", "minimum": 1},
                "type": {"type": "string", "description": "Category filter."},
                "query": {"type": "string", "description": "Text search query."},
            },
            "additionalProperties": False,
        },
        requires_confirmation=False,
    )


def handler(memory: MemoryRepository) -> ToolHandler:
    """Build the registry handler for memory retrieval."""

    async def read(arguments: Mapping[str, Any]) -> str:
        if "memory_id" in arguments:
            return record_json(await memory.get(memory_id(arguments)))
        records = await memory.find(
            type=optional_string(arguments, "type"),
            query=optional_string(arguments, "query"),
        )
        return records_json(records)

    return read
