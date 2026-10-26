"""Tool for creating persistent memory records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolSpec
from sensai.core.models.memory import MEMORY_CATEGORIES
from sensai.core.tools.builtin.memory.utils import (
    find_similar,
    record_json,
    reject_unknown,
    required_string,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolHandler

_FIELDS = frozenset({"name", "type", "description"})


def spec() -> ToolSpec:
    """Describe creation of a durable memory record."""
    return ToolSpec(
        name="memory_create",
        description=(
            "Stores one durable fact about the user, a project, or another "
            "entity. Search existing memories first to avoid duplicates. The "
            "fact itself goes in `description`."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short subject, e.g. 'preferred language'.",
                },
                "type": {
                    "type": "string",
                    "description": (
                        f"Record category: one of {', '.join(MEMORY_CATEGORIES)}."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "The fact itself, e.g. 'Prefers Rust'.",
                },
            },
            "required": ["name", "type", "description"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
    )


def handler(memory: MemoryRepository) -> ToolHandler:
    """Build the registry handler for memory creation."""

    async def create(arguments: Mapping[str, Any]) -> str:
        reject_unknown(arguments, _FIELDS)
        name = required_string(arguments, "name")
        description = required_string(arguments, "description")
        if similar := await find_similar(memory, name):
            raise ValueError(
                f"a memory on this subject already exists (id {similar.id}, "
                f"{similar.name!r}); call memory_update with memory_id={similar.id} "
                "instead of creating another one"
            )
        record = await memory.create(
            name=name,
            type=required_string(arguments, "type"),
            description=description,
        )
        return record_json(record)

    return create
