"""Tests for the SQLite long-term memory repository."""

from __future__ import annotations

import asyncio
import itertools
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from sensai.adapters.storage import sqlite_migrator
from sensai.adapters.storage.repositories import SqliteMemoryRepository
from sensai.adapters.storage.sqlite import SqliteDatabase

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

START = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """Yield a fresh in-memory database with every migration applied."""
    connection = sqlite3.connect(
        ":memory:", check_same_thread=False, isolation_level=None
    )
    connection.execute("PRAGMA foreign_keys=ON")
    sqlite_migrator.apply_migrations(connection)
    yield connection
    connection.close()


def _run(
    conn: sqlite3.Connection,
    scenario: Callable[[SqliteMemoryRepository], Awaitable[None]],
) -> None:
    """Run an asynchronous scenario with a deterministic repository clock."""
    ticks = itertools.count()
    db = SqliteDatabase(conn, clock=lambda: START + timedelta(seconds=next(ticks)))
    asyncio.run(scenario(SqliteMemoryRepository(db)))


def test_find_matches_terms_from_a_natural_language_query(
    conn: sqlite3.Connection,
) -> None:
    """A full user request retrieves records containing one of its terms."""

    async def scenario(repo: SqliteMemoryRepository) -> None:
        await repo.create(
            name="preferred language",
            type="preference",
            description="The user prefers Rust.",
        )
        await repo.create(name="Sensai", type="project", description="Epitech")

        found = await repo.find(query="Which language do I prefer?")

        assert [record.name for record in found] == ["preferred language"]
        assert await repo.find(query="123") == []

    _run(conn, scenario)
