"""Tool for creating persistent memory records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolSpec
from sensai.core.tools.builtin.memory.utils import (
    optional_string,
    record_json,
    required_string,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolHandler


def spec() -> ToolSpec:
    """Describe creation of a durable memory record."""
    return ToolSpec(
        name="memory_create",
        description=(
            "Stores one durable fact about the user, a project, or another "
            "entity. Search existing memories first to avoid duplicates."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Record subject."},
                "type": {"type": "string", "description": "Record category."},
                "description": {
                    "type": "string",
                    "description": "Optional factual details.",
                },
            },
            "required": ["name", "type"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
    )


def handler(memory: MemoryRepository) -> ToolHandler:
    """Build the registry handler for memory creation."""

    async def create(arguments: Mapping[str, Any]) -> str:
        record = await memory.create(
            name=required_string(arguments, "name"),
            type=required_string(arguments, "type"),
            description=optional_string(arguments, "description"),
        )
        return record_json(record)

    return create
