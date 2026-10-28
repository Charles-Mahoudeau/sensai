"""Tests for the token usage saved on SQLite sessions."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from sensai.adapters.storage import sqlite_migrator
from sensai.adapters.storage.repositories import SqliteSessionRepository
from sensai.adapters.storage.sqlite import SqliteDatabase
from sensai.core.models.llm import UsageTotals
from sensai.core.ports import SessionNotFoundError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator


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
    scenario: Callable[[SqliteSessionRepository], Awaitable[None]],
) -> None:
    asyncio.run(scenario(SqliteSessionRepository(SqliteDatabase(conn))))


def test_a_new_session_has_no_usage(conn: sqlite3.Connection) -> None:
    """Every counter starts at zero."""

    async def scenario(repo: SqliteSessionRepository) -> None:
        session = await repo.create_session(model="m")

        assert session.usage == UsageTotals()

    _run(conn, scenario)


def test_add_usage_adds_to_the_saved_totals(conn: sqlite3.Connection) -> None:
    """Each call increments the totals, read back by get and list."""
    first = UsageTotals(
        prompt_tokens=100,
        completion_tokens=20,
        calls=2,
        generation_time=timedelta(milliseconds=1500),
    )
    second = UsageTotals(prompt_tokens=50, completion_tokens=5, calls=1)

    async def scenario(repo: SqliteSessionRepository) -> None:
        session = await repo.create_session(model="m")

        await repo.add_usage(session.id, first)
        await repo.add_usage(session.id, second)

        assert (await repo.get_session(session.id)).usage == first + second
        [listed] = await repo.list_sessions()
        assert listed.usage == first + second

    _run(conn, scenario)


def test_add_usage_to_an_unknown_session_fails(conn: sqlite3.Connection) -> None:
    """Usage cannot be saved for a session that does not exist."""

    async def scenario(repo: SqliteSessionRepository) -> None:
        with pytest.raises(SessionNotFoundError):
            await repo.add_usage(42, UsageTotals(calls=1))

    _run(conn, scenario)
