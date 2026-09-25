"""SQLite implementation of the `MemoryStore` port."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from sensai.adapters.memory._sqlite import SqliteStore, from_db_time
from sensai.core.models.memory import MemoryRecord
from sensai.core.ports import DuplicateMemoryError, MemoryNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from sensai.core.ports import MemoryStore

_COLUMNS = "id, name, type, created_at, updated_at, description"


def _to_record(row: Sequence[Any]) -> MemoryRecord:
    id_, name, type_, created_at, updated_at, description = row
    return MemoryRecord(
        id_,
        name,
        type_,
        from_db_time(created_at),
        from_db_time(updated_at),
        description,
    )


def _lower(text: str | None) -> str | None:
    """Unicode-aware `lower`; SQLite's own `lower` only folds ASCII."""
    return None if text is None else text.lower()


def _is_duplicate(error: sqlite3.IntegrityError) -> bool:
    return error.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE"


class SqliteMemoryStore(SqliteStore):
    """Stores long-term memory records in the `memories` table."""

    def __init__(
        self, conn: sqlite3.Connection, clock: Callable[[], datetime] | None = None
    ) -> None:
        """Wrap a migrated connection and register the text-search function.

        Args:
            conn: The connection, already migrated. Give each store its own.
            clock: Supplies timestamps; the current UTC time by default.
        """
        super().__init__(conn, clock)
        conn.create_function("sensai_lower", 1, _lower, deterministic=True)

    async def create(
        self, *, name: str, type: str, description: str | None = None
    ) -> MemoryRecord:
        """Insert a record, refusing a duplicate name and type."""

        def create() -> MemoryRecord:
            now = self._now()
            try:
                with self._write() as conn:
                    row = conn.execute(
                        "INSERT INTO memories"
                        " (name, type, description, created_at, updated_at)"
                        f" VALUES (?, ?, ?, ?, ?) RETURNING {_COLUMNS}",
                        (name, type, description, now, now),
                    ).fetchone()
                    return _to_record(row)
            except sqlite3.IntegrityError as error:
                if _is_duplicate(error):
                    raise DuplicateMemoryError(f"{type}/{name}") from error
                raise

        return await self._run(create)

    async def get(self, memory_id: int) -> MemoryRecord:
        """Return a record or raise `MemoryNotFoundError`."""

        def get() -> MemoryRecord:
            row = self._conn.execute(
                f"SELECT {_COLUMNS} FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(memory_id)
            return _to_record(row)

        return await self._run(get)

    async def find(
        self, *, type: str | None = None, query: str | None = None
    ) -> Sequence[MemoryRecord]:
        """Return matching records, most recently updated first."""

        def find() -> list[MemoryRecord]:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM memories"
                " WHERE (:type IS NULL OR type = :type)"
                " AND (:query IS NULL"
                "      OR instr(sensai_lower(name), sensai_lower(:query)) > 0"
                "      OR instr(sensai_lower(coalesce(description, '')),"
                "               sensai_lower(:query)) > 0)"
                " ORDER BY updated_at DESC, id DESC",
                {"type": type, "query": query},
            ).fetchall()
            return [_to_record(row) for row in rows]

        return await self._run(find)

    async def update(
        self,
        memory_id: int,
        *,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
    ) -> MemoryRecord:
        """Change the given fields; `None` keeps the current value."""

        def update() -> MemoryRecord:
            try:
                with self._write() as conn:
                    row = conn.execute(
                        "UPDATE memories SET name = coalesce(?, name),"
                        " type = coalesce(?, type),"
                        " description = coalesce(?, description), updated_at = ?"
                        f" WHERE id = ? RETURNING {_COLUMNS}",
                        (name, type, description, self._now(), memory_id),
                    ).fetchone()
                    if row is None:
                        raise MemoryNotFoundError(memory_id)
                    return _to_record(row)
            except sqlite3.IntegrityError as error:
                if _is_duplicate(error):
                    raise DuplicateMemoryError(
                        f"memory {memory_id}: {error}"
                    ) from error
                raise

        return await self._run(update)

    async def delete(self, memory_id: int) -> None:
        """Delete a record or raise `MemoryNotFoundError`."""

        def delete() -> None:
            with self._write() as conn:
                deleted = conn.execute(
                    "DELETE FROM memories WHERE id = ?", (memory_id,)
                ).rowcount
                if not deleted:
                    raise MemoryNotFoundError(memory_id)

        await self._run(delete)


if TYPE_CHECKING:

    def _conforms(store: SqliteMemoryStore) -> MemoryStore:
        return store
