"""Tool for deleting persistent memory records."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolSpec
from sensai.core.tools.builtin.memory.utils import memory_id

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolHandler


def spec() -> ToolSpec:
    """Describe deletion of a memory record."""
    return ToolSpec(
        name="memory_delete",
        description="Deletes one obsolete or incorrect memory by id.",
        parameters={
            "type": "object",
            "properties": {"memory_id": {"type": "integer", "minimum": 1}},
            "required": ["memory_id"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
    )


def handler(memory: MemoryRepository) -> ToolHandler:
    """Build the registry handler for memory deletion."""

    async def delete(arguments: Mapping[str, Any]) -> str:
        await memory.delete(memory_id(arguments))
        return json.dumps({"deleted": True})

    return delete
