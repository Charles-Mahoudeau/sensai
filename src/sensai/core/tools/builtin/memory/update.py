"""Tool for updating persistent memory records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolSpec
from sensai.core.tools.builtin.memory.utils import (
    memory_id,
    optional_string,
    record_json,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolHandler


def spec() -> ToolSpec:
    """Describe a partial update of a memory record."""
    return ToolSpec(
        name="memory_update",
        description=(
            "Changes an existing memory after finding it by id. Provide only the "
            "fields that should change; use an empty description to clear it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer", "minimum": 1},
                "name": {"type": "string"},
                "type": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["memory_id"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
    )


def handler(memory: MemoryRepository) -> ToolHandler:
    """Build the registry handler for memory updates."""

    async def update(arguments: Mapping[str, Any]) -> str:
        fields = ("name", "type", "description")
        if not any(field in arguments for field in fields):
            raise ValueError("memory_update requires at least one field to change")
        record = await memory.update(
            memory_id(arguments),
            name=optional_string(arguments, "name"),
            type=optional_string(arguments, "type"),
            description=optional_string(arguments, "description"),
        )
        return record_json(record)

    return update
