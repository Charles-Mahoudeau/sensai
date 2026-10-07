"""Tests for persistent-memory tools."""

from __future__ import annotations

import asyncio
import json

from sensai.core.models import ToolCall
from sensai.core.tools.builtin import memory
from sensai.core.tools.permissions import DenyAll
from sensai.core.tools.registry import ToolRegistry
from tests.fakes.memory import InMemoryMemoryStore


def test_memory_tools_cover_crud_operations() -> None:
    """Every memory operation is dispatched through the shared registry."""

    async def run() -> None:
        registry = ToolRegistry()
        memory.register_self(registry, InMemoryMemoryStore())

        assert {spec.name for spec in registry.spec()} == {
            "memory_create",
            "memory_read",
            "memory_update",
            "memory_delete",
        }

        created = await registry.call(
            ToolCall(
                "memory_create",
                {"name": "Python", "type": "language", "description": "Preferred"},
                "create-1",
            )
        )
        record = json.loads(created.content)
        assert record["id"] == 1
        assert record["description"] == "Preferred"

        found = await registry.call(
            ToolCall("memory_read", {"query": "python"}, "read-1")
        )
        assert json.loads(found.content)["records"] == [record]

        updated = await registry.call(
            ToolCall(
                "memory_update",
                {"memory_id": record["id"], "description": "Primary language"},
                "update-1",
            )
        )
        assert json.loads(updated.content)["description"] == "Primary language"

        deleted = await registry.call(
            ToolCall("memory_delete", {"memory_id": record["id"]}, "delete-1")
        )
        assert json.loads(deleted.content) == {"deleted": True}

    asyncio.run(run())


def test_memory_tools_respect_the_registry_permission_policy() -> None:
    """The handler is not called when the shared registry denies a request."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry(permissions=DenyAll())
        memory.register_self(registry, store)

        result = await registry.call(
            ToolCall("memory_create", {"name": "Python", "type": "language"})
        )

        assert result.is_error
        assert "Permission denied" in result.content
        assert await store.find() == []

    asyncio.run(run())
