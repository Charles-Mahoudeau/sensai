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


def test_memory_read_requires_a_filter_and_limits_results() -> None:
    """Memory search cannot expose every record and returns a bounded result set."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)
        for index in range(3):
            await store.create(name=f"language-{index}", type="preference")

        unfiltered = await registry.call(ToolCall("memory_read", {}))
        limited = await registry.call(
            ToolCall("memory_read", {"query": "language", "limit": 2})
        )

        assert unfiltered.is_error
        assert "requires memory_id, type, or query" in unfiltered.content
        assert len(json.loads(limited.content)["records"]) == 2

    asyncio.run(run())


def test_memory_tools_accept_integers_sent_as_strings() -> None:
    """Small models send `"2"` for numbers; digit strings work, junk is rejected."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)
        for index in range(3):
            await store.create(name=f"language-{index}", type="preference")

        limited = await registry.call(
            ToolCall("memory_read", {"query": "language", "limit": "2"})
        )
        by_id = await registry.call(ToolCall("memory_read", {"memory_id": "1"}))
        junk = await registry.call(
            ToolCall("memory_read", {"query": "language", "limit": "None"})
        )
        junk_id = await registry.call(ToolCall("memory_read", {"memory_id": "None"}))

        assert len(json.loads(limited.content)["records"]) == 2
        assert json.loads(by_id.content)["id"] == 1
        assert junk.is_error
        assert junk_id.is_error

    asyncio.run(run())


def test_memory_create_requires_the_fact_and_rejects_unknown_arguments() -> None:
    """A record without its fact, or with a misplaced one, is refused."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)

        no_fact = await registry.call(
            ToolCall("memory_create", {"name": "language", "type": "preference"})
        )
        blank_fact = await registry.call(
            ToolCall(
                "memory_create",
                {"name": "language", "type": "preference", "description": ""},
            )
        )
        misplaced = await registry.call(
            ToolCall(
                "memory_create",
                {
                    "name": "language",
                    "type": "preference",
                    "description": "Prefers Rust",
                    "langage": "Rust",
                },
            )
        )

        assert no_fact.is_error
        assert blank_fact.is_error
        assert misplaced.is_error
        assert "langage" in misplaced.content
        assert await store.find() == []

    asyncio.run(run())


def test_memory_create_points_to_an_existing_record_on_the_same_subject() -> None:
    """A reworded name is a duplicate: the error tells which record to update."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)
        first = await registry.call(
            ToolCall(
                "memory_create",
                {
                    "name": "préférence de langage de programmation",
                    "type": "preference",
                    "description": "Prefers Python",
                },
            )
        )
        reworded = await registry.call(
            ToolCall(
                "memory_create",
                {
                    "name": "langage de programmation préféré",
                    "type": "preference",
                    "description": "Prefers Rust",
                },
            )
        )
        other = await registry.call(
            ToolCall(
                "memory_create",
                {"name": "couleur", "type": "preference", "description": "Blue"},
            )
        )

        assert not first.is_error
        assert reworded.is_error
        assert "memory_update" in reworded.content
        assert not other.is_error

    asyncio.run(run())


def test_memory_update_rejects_unknown_arguments_and_blank_facts() -> None:
    """An update cannot drop data silently or wipe the fact."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)
        record = await store.create(
            name="language", type="preference", description="Prefers Python"
        )

        unknown = await registry.call(
            ToolCall("memory_update", {"memory_id": record.id, "langage": "Rust"})
        )
        blank = await registry.call(
            ToolCall("memory_update", {"memory_id": record.id, "description": ""})
        )

        assert unknown.is_error
        assert blank.is_error
        assert (await store.get(record.id)).description == "Prefers Python"

    asyncio.run(run())


def test_memory_read_treats_blank_filters_as_absent() -> None:
    """An empty `query` next to a real `type` is not an error."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        registry = ToolRegistry()
        memory.register_self(registry, store)
        await store.create(name="language", type="preference", description="Rust")

        result = await registry.call(
            ToolCall("memory_read", {"type": "preference", "query": ""})
        )
        nothing = await registry.call(ToolCall("memory_read", {"query": " "}))

        assert len(json.loads(result.content)["records"]) == 1
        assert nothing.is_error

    asyncio.run(run())


def test_memory_results_keep_accents_readable() -> None:
    """Tool results show accented words as they are, not as escapes."""

    async def run() -> tuple[str, str]:
        registry = ToolRegistry()
        memory.register_self(registry, InMemoryMemoryStore())
        created = await registry.call(
            ToolCall(
                "memory_create",
                {
                    "name": "voiture préférée",
                    "type": "preference",
                    "description": "Préfère les voitures BMW.",
                },
            )
        )
        found = await registry.call(ToolCall("memory_read", {"query": "voiture"}))
        return created.content, found.content

    created, found = asyncio.run(run())

    for content in (created, found):
        assert "voiture préférée" in content
        assert "\\u00e9" not in content
