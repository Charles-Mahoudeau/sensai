"""Applying the numbered `.sql` migrations to a database, in order."""

from __future__ import annotations

import sqlite3
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

MIGRATIONS = resources.files("sensai.adapters.storage") / "migrations"

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


class MigrationError(Exception):
    """The migration files or the database's migration history are invalid."""


def _numbered_scripts(folder: Traversable) -> list[tuple[int, Traversable]]:
    """Return the `NNN_name.sql` files sorted by version, refusing any gap."""
    scripts: list[tuple[int, Traversable]] = []
    for entry in folder.iterdir():
        if not entry.name.endswith(".sql"):
            continue
        prefix = entry.name.split("_", 1)[0]
        if not prefix.isdigit():
            raise MigrationError(f"migration {entry.name!r} has no version prefix")
        scripts.append((int(prefix), entry))
    scripts.sort(key=lambda script: script[0])
    versions = [version for version, _ in scripts]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f"migration versions must be 1, 2, 3...; got {versions}")
    return scripts


def migrate(conn: sqlite3.Connection, folder: Traversable = MIGRATIONS) -> list[int]:
    """Apply every migration the database has not seen yet.

    Each migration runs in its own transaction together with its
    `schema_migrations` row, so a failing script leaves no trace.

    Args:
        conn: A connection opened with `connect`.
        folder: The directory holding the `NNN_name.sql` files.

    Returns:
        The versions applied by this call, in order.

    Raises:
        MigrationError: The files are misnumbered, or the database has
            applied a version that no longer exists in `folder`.
        sqlite3.Error: A migration script failed; it was rolled back.
    """
    scripts = _numbered_scripts(folder)
    conn.executescript(_BOOTSTRAP)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    unknown = applied - {version for version, _ in scripts}
    if unknown:
        raise MigrationError(f"database has unknown migrations {sorted(unknown)}")

    newly_applied: list[int] = []
    for version, script in scripts:
        if version in applied:
            continue
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{script.read_text(encoding='utf-8')}\n;\n"
                f"INSERT INTO schema_migrations (version) VALUES ({version});\n"
                "COMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        newly_applied.append(version)
    return newly_applied
