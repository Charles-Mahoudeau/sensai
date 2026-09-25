"""Tests for behavior specific to the SQLite session and memory stores.

The port contract itself is covered by `tests/core/ports/test_memory.py`,
which runs against these stores too.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.adapters.memory import SqliteMemoryStore, SqliteSessionStore
from sensai.adapters.storage import connect, migrate
from sensai.core.models.llm import Message
from sensai.core.ports import StorageError

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """A migrated in-memory database."""
    connection = connect(":memory:")
    migrate(connection)
    yield connection
    connection.close()


def test_messages_are_chained_through_parent_id(conn: sqlite3.Connection) -> None:
    """Each appended message points at the previous one of its session."""
    store = SqliteSessionStore(conn)

    async def run() -> None:
        first = await store.create_session(model="m")
        other = await store.create_session(model="m")
        await store.append_message(first.id, Message.user("a"))
        await store.append_message(other.id, Message.user("x"))
        await store.append_message(first.id, Message.assistant("b"))

    asyncio.run(run())

    rows = conn.execute(
        "SELECT id, session_id, parent_id FROM messages ORDER BY id"
    ).fetchall()
    assert rows == [(1, 1, None), (2, 2, None), (3, 1, 1)]


def test_delete_session_cascades_to_messages(conn: sqlite3.Connection) -> None:
    """Deleting a session removes its message rows too."""
    store = SqliteSessionStore(conn)

    async def run() -> None:
        session = await store.create_session(model="m")
        await store.append_message(session.id, Message.user("hi"))
        await store.delete_session(session.id)

    asyncio.run(run())

    assert conn.execute("SELECT count(*) FROM messages").fetchone() == (0,)


def test_data_survives_reopening_the_file(tmp_path: Path) -> None:
    """Sessions, profile and memories are read back from a fresh connection."""
    path = tmp_path / "sensai.db"
    first = connect(path)
    migrate(first)

    async def write() -> int:
        sessions = SqliteSessionStore(first)
        session = await sessions.create_session(model="llama3", title="Hi")
        await sessions.append_message(session.id, Message.user("Bonjour"))
        await sessions.set_profile_value("language", "fr")
        await SqliteMemoryStore(first).create(name="Ada", type="person")
        return session.id

    session_id = asyncio.run(write())
    first.close()
    second = connect(path)

    async def read() -> tuple[object, ...]:
        sessions = SqliteSessionStore(second)
        return (
            (await sessions.get_session(session_id)).title,
            list(await sessions.get_messages(session_id)),
            dict(await sessions.get_profile()),
            [r.name for r in await SqliteMemoryStore(second).find()],
        )

    try:
        result = asyncio.run(read())
    finally:
        second.close()

    assert result == (
        "Hi",
        [Message.user("Bonjour")],
        {"language": "fr"},
        ["Ada"],
    )


def test_timestamps_are_stored_as_utc_iso_text(conn: sqlite3.Connection) -> None:
    """Rows use the schema's `%Y-%m-%dT%H:%M:%fZ` format."""
    asyncio.run(SqliteSessionStore(conn).create_session(model="m"))

    (created_at,) = conn.execute("SELECT created_at FROM sessions").fetchone()
    assert created_at.endswith("Z")
    assert len(created_at) == len("2026-01-01T00:00:00.000Z")


def test_invalid_record_is_not_written(conn: sqlite3.Connection) -> None:
    """A value the model rejects rolls the insert back."""
    store = SqliteMemoryStore(conn)

    with pytest.raises(ValueError, match="name"):
        asyncio.run(store.create(name="", type="person"))

    assert conn.execute("SELECT count(*) FROM memories").fetchone() == (0,)


def test_sqlite_failures_become_storage_errors(conn: sqlite3.Connection) -> None:
    """Callers never see `sqlite3` exceptions."""
    store = SqliteMemoryStore(conn)
    conn.close()

    with pytest.raises(StorageError):
        asyncio.run(store.find())
