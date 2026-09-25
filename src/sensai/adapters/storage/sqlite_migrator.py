"""Script to interact with SQLite migrations."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

from sensai.adapters.storage.constants import (
    DB_FILE,
    MIGRATIONS_DIR,
    MIGRATIONS_START_ID,
)

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator

MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY NOT NULL,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def nuke_database() -> None:
    """Deletes the database file along with its WAL and SHM sidecar files.

    All SQLite connections to the database must be closed before calling this,
    otherwise the sidecars may be recreated or stale state may remain.
    """
    for suffix in ("", "-wal", "-shm"):
        DB_FILE.with_name(DB_FILE.name + suffix).unlink(missing_ok=True)


def create_migration(name: str) -> Path:
    """Creates a new migration file.

    Args:
        name: Name of the migration.

    Returns:
        Path to the created migration file.
    """
    _ensure_dir_exists(MIGRATIONS_DIR)
    migration_id = _get_next_migration_id()
    path = Path(f"{MIGRATIONS_DIR}/{migration_id}_{name}.sql")
    with path.open("x") as f:
        f.writelines(
            [
                "--\n",
                "-- Database migration file.\n",
                "--\n"
                "-- Write your migration here in sqlite3 format.\n"
                "-- Be careful, no rollbacks are possible.\n"
                "--\n",
            ]
        )
    return path


def _get_latest_migration_id() -> int:
    if not MIGRATIONS_DIR.exists():
        return -1
    return max((mid for mid, _ in _get_filesystem_migrations()), default=-1)


def _get_next_migration_id() -> int:
    latest_id = _get_latest_migration_id()
    if latest_id < 0:
        return MIGRATIONS_START_ID
    return latest_id + 1


def _ensure_dir_exists(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True)


def apply_migrations(db_connection: sqlite3.Connection) -> None:
    """Applies all pending migrations to the given database connection.

    Args:
        db_connection: Database connection to apply migrations to.
    """
    if check_migrations_state(db_connection):
        # Already up to date.
        return
    applied = {row[0] for row in db_connection.execute("SELECT id FROM migrations")}
    for migration_id, migration_file in _get_filesystem_migrations():
        if migration_id in applied:
            continue
        _apply_migration_file(db_connection, migration_file)


def _apply_migration_file(db_connection: sqlite3.Connection, path: Path) -> None:
    migration_id = _get_migration_id_from_filename(path.stem)
    with path.open("r") as f:
        migration_sql = f.read()
    try:
        db_connection.execute("BEGIN")
        for sql in migration_sql.split(";"):
            db_connection.execute(sql)
        db_connection.execute("INSERT INTO migrations(id) VALUES (?)", (migration_id,))
        db_connection.execute("COMMIT")
    except Exception as e:
        db_connection.execute("ROLLBACK")
        raise RuntimeError(f"error applying migration {path}: {e}") from e


def _get_filesystem_migrations() -> Iterator[tuple[int, Path]]:
    migrations = [
        (_get_migration_id_from_filename(migration_file.stem), migration_file)
        for migration_file in MIGRATIONS_DIR.glob("*.sql")
    ]
    yield from sorted(migrations, key=lambda migration: migration[0])


def _get_migration_id_from_filename(filename: str) -> int:
    match = re.match(r"^(\d+)", filename)
    if not match:
        raise ValueError(f"filename {filename} has no numeric id prefix")
    return int(match.group(1))


def check_migrations_state(db_connection: sqlite3.Connection) -> bool:
    """Check if migrations are up to date.

    Check that the migration files are without gaps and that the migration table is up
     to date.

    Args:
            db_connection: The database connection to check.

    Returns:
        True if the migrations are up to date, False otherwise.

    Raises:
            ValueError: If the migration files are not up to date.
    """
    _bootstrap_migrations(db_connection)

    # Detect a gap inside the migration files.
    last_file_id = None

    for index, (migration_id, _) in enumerate(_get_filesystem_migrations()):
        if migration_id != index:
            raise ValueError(f"missing migration file, id: {index}")
        last_file_id = migration_id

    # Detect a gap inside the migration table.
    last_table_id = None

    cursor = db_connection.execute("SELECT id FROM migrations ORDER BY id")
    for row_id, row in enumerate(cursor):
        migration_id = row[0]
        if migration_id != row_id:
            raise ValueError(f"missing migration in table, id: {row_id}")
        last_table_id = migration_id

    # Both sequences are gap-free from 0, so a longer table means recorded
    # migrations with no corresponding file.
    # noinspection unsupported-operator
    if last_table_id is not None and (
        last_file_id is None or last_table_id > last_file_id
    ):
        raise ValueError(
            f"migration table records id {last_table_id} with no migration file"
        )

    return last_file_id == last_table_id


def _bootstrap_migrations(db_connection: sqlite3.Connection) -> None:
    _ensure_dir_exists(MIGRATIONS_DIR)
    with db_connection:
        db_connection.executescript(MIGRATIONS_TABLE_SQL)
