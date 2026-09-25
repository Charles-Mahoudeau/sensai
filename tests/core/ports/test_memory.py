"""Tests for the session and memory port contracts, through the fakes."""

from __future__ import annotations

import asyncio

import pytest

from sensai.core.models.llm import Message
from sensai.core.ports import (
    DuplicateMemoryError,
    MemoryNotFoundError,
    SessionNotFoundError,
    StorageError,
)
from tests.fakes import InMemoryMemoryStore, InMemorySessionStore


def test_messages_come_back_in_order() -> None:
    """A resumed session gets its messages oldest first, unchanged."""
    store = InMemorySessionStore()
    history = [Message.user("Hi"), Message.assistant("Hello!")]

    async def run() -> list[Message]:
        session = await store.create_session(model="llama3")
        for message in history:
            await store.append_message(session.id, message)
        return list(await store.get_messages(session.id))

    assert asyncio.run(run()) == history


def test_unknown_session_raises() -> None:
    """Every session method reports an unknown id the same way."""
    store = InMemorySessionStore()

    for call in (
        store.get_session(99),
        store.get_messages(99),
        store.append_message(99, Message.user("x")),
        store.delete_session(99),
    ):
        with pytest.raises(SessionNotFoundError):
            asyncio.run(call)


def test_list_sessions_puts_the_latest_activity_first() -> None:
    """Appending a message moves its session to the top of the list."""
    store = InMemorySessionStore()

    async def run() -> list[int]:
        first = await store.create_session(model="m", title="old")
        second = await store.create_session(model="m", title="new")
        await store.append_message(first.id, Message.user("bump"))
        return [s.id for s in await store.list_sessions()] + [second.id]

    assert asyncio.run(run()) == [1, 2, 2]


def test_list_sessions_respects_limit() -> None:
    """`limit` caps the number of sessions returned."""
    store = InMemorySessionStore()

    async def run() -> int:
        for _ in range(3):
            await store.create_session(model="m")
        return len(await store.list_sessions(limit=2))

    assert asyncio.run(run()) == 2


def test_delete_session_removes_it() -> None:
    """A deleted session can't be read any more."""
    store = InMemorySessionStore()

    async def run() -> None:
        session = await store.create_session(model="m")
        await store.delete_session(session.id)
        await store.get_session(session.id)

    with pytest.raises(SessionNotFoundError):
        asyncio.run(run())


def test_profile_set_replace_and_delete() -> None:
    """Profile entries can be created, replaced and removed."""
    store = InMemorySessionStore()

    async def run() -> tuple[dict[str, str], dict[str, str]]:
        await store.set_profile_value("language", "fr")
        await store.set_profile_value("language", "en")
        await store.set_profile_value("editor", "vim")
        before = dict(await store.get_profile())
        await store.delete_profile_value("editor")
        await store.delete_profile_value("missing")  # no-op
        return before, dict(await store.get_profile())

    before, after = asyncio.run(run())

    assert before == {"language": "en", "editor": "vim"}
    assert after == {"language": "en"}


def test_memory_create_get_and_duplicate() -> None:
    """A record can be read back, and name + type must be unique."""
    store = InMemoryMemoryStore()

    async def run() -> None:
        record = await store.create(name="Ada", type="person", description="Dev")
        assert await store.get(record.id) == record
        await store.create(name="Ada", type="project")  # same name, other type
        await store.create(name="Ada", type="person")

    with pytest.raises(DuplicateMemoryError):
        asyncio.run(run())


def test_memory_find_by_type_and_query() -> None:
    """`find` filters by type and by case-insensitive text in name or description."""
    store = InMemoryMemoryStore()

    async def run() -> tuple[list[str], list[str], list[str]]:
        await store.create(name="Ada", type="person", description="Loves Python")
        await store.create(name="Sensai", type="project", description="Epitech")
        await store.create(name="Python", type="concept")
        by_type = [r.name for r in await store.find(type="person")]
        by_query = [r.name for r in await store.find(query="python")]
        both = [r.name for r in await store.find(type="concept", query="python")]
        return by_type, sorted(by_query), both

    by_type, by_query, both = asyncio.run(run())

    assert by_type == ["Ada"]
    assert by_query == ["Ada", "Python"]
    assert both == ["Python"]


def test_memory_update_changes_only_given_fields() -> None:
    """`None` keeps a field, an empty string clears the description."""
    store = InMemoryMemoryStore()

    async def run() -> tuple[str | None, str | None]:
        record = await store.create(name="Ada", type="person", description="Dev")
        renamed = await store.update(record.id, name="Ada L.")
        cleared = await store.update(record.id, description="")
        return renamed.description, cleared.description

    kept, cleared = asyncio.run(run())

    assert kept == "Dev"
    assert cleared == ""


def test_memory_update_refreshes_updated_at_only() -> None:
    """Updating moves `updated_at` forward and leaves `created_at` alone."""
    store = InMemoryMemoryStore()

    async def run() -> tuple[bool, bool]:
        record = await store.create(name="Ada", type="person")
        changed = await store.update(record.id, description="Dev")
        return changed.created_at == record.created_at, (
            changed.updated_at > record.updated_at
        )

    assert asyncio.run(run()) == (True, True)


def test_memory_update_cannot_collide_with_another_record() -> None:
    """Renaming onto an existing name + type is refused."""
    store = InMemoryMemoryStore()

    async def run() -> None:
        await store.create(name="Ada", type="person")
        other = await store.create(name="Bob", type="person")
        await store.update(other.id, name="Ada")

    with pytest.raises(DuplicateMemoryError):
        asyncio.run(run())


def test_memory_unknown_id_raises() -> None:
    """The agent is told when it uses an id that doesn't exist."""
    store = InMemoryMemoryStore()

    for call in (store.get(9), store.update(9, name="x"), store.delete(9)):
        with pytest.raises(MemoryNotFoundError):
            asyncio.run(call)


def test_memory_delete_removes_the_record() -> None:
    """A deleted record can't be fetched again."""
    store = InMemoryMemoryStore()

    async def run() -> None:
        record = await store.create(name="Ada", type="person")
        await store.delete(record.id)
        await store.get(record.id)

    with pytest.raises(MemoryNotFoundError):
        asyncio.run(run())


def test_storage_errors_share_a_base_class() -> None:
    """Callers can catch every store failure with StorageError."""
    for error in (SessionNotFoundError, MemoryNotFoundError, DuplicateMemoryError):
        assert issubclass(error, StorageError)
