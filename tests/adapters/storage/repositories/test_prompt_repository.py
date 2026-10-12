"""Tests for the SQLite prompt repository, on a migrated in-memory database."""

from __future__ import annotations

import asyncio
import itertools
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from sensai.adapters.storage import sqlite_migrator
from sensai.adapters.storage.repositories import SqlitePromptRepository
from sensai.adapters.storage.sqlite import SqliteDatabase
from sensai.core.ports import PromptNotFoundError, PromptVersionNotFoundError

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
    scenario: Callable[[SqlitePromptRepository], Awaitable[None]],
) -> None:
    ticks = itertools.count()
    db = SqliteDatabase(conn, clock=lambda: START + timedelta(seconds=next(ticks)))
    asyncio.run(scenario(SqlitePromptRepository(db)))


def test_versions_are_numbered_per_prompt(conn: sqlite3.Connection) -> None:
    """Each prompt has its own version sequence, starting at 1."""

    async def scenario(repo: SqlitePromptRepository) -> None:
        first = await repo.create_version("system", "one", note="first")
        second = await repo.create_version("system", "two")
        judge = await repo.create_version("judge", "judge")

        assert (first.version, second.version, judge.version) == (1, 2, 1)
        assert first.note == "first"
        assert second.note is None
        assert first.created_at == START
        assert [p.content for p in await repo.list_versions("system")] == [
            "one",
            "two",
        ]

    _run(conn, scenario)


def test_get_version_and_unknown_version(conn: sqlite3.Connection) -> None:
    """A stored version is returned; an unknown one raises."""

    async def scenario(repo: SqlitePromptRepository) -> None:
        await repo.create_version("system", "one")

        assert (await repo.get_version("system", 1)).content == "one"
        with pytest.raises(PromptVersionNotFoundError):
            await repo.get_version("system", 2)

    _run(conn, scenario)


def test_find_by_content_returns_the_latest_match(conn: sqlite3.Connection) -> None:
    """Only exact content matches, and the newest matching version wins."""

    async def scenario(repo: SqlitePromptRepository) -> None:
        await repo.create_version("system", "same")
        await repo.create_version("system", "other")
        await repo.create_version("system", "same")

        found = await repo.find_by_content("system", "same")
        assert found is not None
        assert found.version == 3
        assert await repo.find_by_content("system", "missing") is None
        assert await repo.find_by_content("judge", "same") is None

    _run(conn, scenario)


def test_active_version_can_be_switched(conn: sqlite3.Connection) -> None:
    """`set_active` replaces the active version of a prompt."""

    async def scenario(repo: SqlitePromptRepository) -> None:
        await repo.create_version("system", "one")
        await repo.create_version("system", "two")
        await repo.create_version("judge", "judge")

        with pytest.raises(PromptNotFoundError):
            await repo.get_active("system")

        await repo.set_active("system", 2)
        await repo.set_active("judge", 1)
        await repo.set_active("system", 1)

        assert (await repo.get_active("system")).content == "one"
        assert [(p.name, p.version) for p in await repo.list_active()] == [
            ("judge", 1),
            ("system", 1),
        ]

    _run(conn, scenario)


def test_activating_an_unknown_version_raises(conn: sqlite3.Connection) -> None:
    """An unknown version can't become active."""

    async def scenario(repo: SqlitePromptRepository) -> None:
        await repo.create_version("system", "one")

        with pytest.raises(PromptVersionNotFoundError):
            await repo.set_active("system", 5)

    _run(conn, scenario)


def test_schema_rejects_an_active_version_that_doesnt_exist(
    conn: sqlite3.Connection,
) -> None:
    """The foreign key keeps `active_prompts` pointing at real versions."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO active_prompts (name, version) VALUES ('x', 1)")
