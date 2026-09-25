"""Tests for the migration runner and the schema the migrations create."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from sensai.adapters.storage import MIGRATIONS, MigrationError, connect, migrate

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

EXPECTED_TABLES = {
    "schema_migrations",
    "sessions",
    "messages",
    "user_profile",
    "memories",
}


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """An empty, unmigrated in-memory database."""
    connection = connect(":memory:")
    yield connection
    connection.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
    return {name for (name,) in rows}


def _write(folder: Path, files: dict[str, str]) -> Path:
    for name, sql in files.items():
        (folder / name).write_text(sql)
    return folder


def test_real_migrations_apply_on_an_empty_database(conn: sqlite3.Connection) -> None:
    """Every shipped migration runs, in order, and is recorded."""
    applied = migrate(conn)

    assert applied == list(range(1, len(applied) + 1))
    assert _tables(conn) == EXPECTED_TABLES
    recorded = [v for (v,) in conn.execute("SELECT version FROM schema_migrations")]
    assert recorded == applied


def test_shipped_migrations_have_no_gap() -> None:
    """The files in the package are numbered 001, 002, 003… without holes."""
    names = sorted(e.name for e in MIGRATIONS.iterdir() if e.name.endswith(".sql"))
    versions = [int(name.split("_", 1)[0]) for name in names]
    assert versions == list(range(1, len(versions) + 1))


def test_migrate_twice_applies_nothing_new(conn: sqlite3.Connection) -> None:
    """Running the migrations again on an up-to-date database is a no-op."""
    migrate(conn)

    assert migrate(conn) == []


def test_only_missing_migrations_are_applied(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A database migrated earlier only receives the newer files."""
    _write(tmp_path, {"001_a.sql": "CREATE TABLE a (x INTEGER) STRICT;"})
    migrate(conn, tmp_path)
    _write(tmp_path, {"002_b.sql": "CREATE TABLE b (x INTEGER) STRICT;"})

    assert migrate(conn, tmp_path) == [2]


def test_failing_migration_is_rolled_back(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A broken script leaves neither its tables nor its version behind."""
    _write(
        tmp_path,
        {
            "001_ok.sql": "CREATE TABLE ok (x INTEGER) STRICT;",
            "002_broken.sql": "CREATE TABLE half (x INTEGER) STRICT; NOT SQL;",
        },
    )

    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, tmp_path)

    assert "half" not in _tables(conn)
    assert [v for (v,) in conn.execute("SELECT version FROM schema_migrations")] == [1]
    assert not conn.in_transaction


@pytest.mark.parametrize(
    "files",
    [
        {"001_a.sql": "", "003_c.sql": ""},
        {"002_b.sql": ""},
        {"a.sql": ""},
    ],
)
def test_misnumbered_files_are_refused(
    conn: sqlite3.Connection, tmp_path: Path, files: dict[str, str]
) -> None:
    """Gaps and missing prefixes are caught before anything runs."""
    with pytest.raises(MigrationError):
        migrate(conn, _write(tmp_path, files))


def test_database_newer_than_the_code_is_refused(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A version applied to the database but missing from disk is an error."""
    _write(tmp_path, {"001_a.sql": "", "002_b.sql": ""})
    migrate(conn, tmp_path)
    (tmp_path / "002_b.sql").unlink()

    with pytest.raises(MigrationError):
        migrate(conn, tmp_path)


def test_connect_enables_foreign_keys_and_wal(tmp_path: Path) -> None:
    """The pragmas the schema relies on are set on every connection."""
    file_conn = connect(tmp_path / "sensai.db")

    try:
        assert file_conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert file_conn.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        file_conn.close()


def test_schema_rejects_invalid_values(conn: sqlite3.Connection) -> None:
    """CHECK constraints guard enums, booleans and JSON columns."""
    migrate(conn)
    conn.execute("INSERT INTO sessions (id, model) VALUES (1, 'm')")

    for statement in (
        "INSERT INTO sessions (model, mode) VALUES ('m', 'dream')",
        "INSERT INTO sessions (model, thinking) VALUES ('m', 2)",
        "INSERT INTO messages (session_id, role) VALUES (1, 'robot')",
        "INSERT INTO messages (session_id, role, tool_calls_json)"
        " VALUES (1, 'assistant', '{not json')",
        "INSERT INTO messages (session_id, role) VALUES (42, 'user')",
        "INSERT INTO user_profile (key, value, category) VALUES ('k', 'v', 'x')",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)
