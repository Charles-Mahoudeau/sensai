"""SQLite repository for versioned prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.adapters.storage.sqlite import SqliteDatabase, from_db_time
from sensai.core.models.prompts import PromptVersion
from sensai.core.ports import PromptNotFoundError, PromptVersionNotFoundError

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Sequence

_TABLE = "prompt_versions"


class SqlitePromptRepository:
    """Stores prompt versions and the active version of each prompt."""

    def __init__(self, db: SqliteDatabase) -> None:
        """Read the table's columns from the migrated schema.

        Args:
            db: The database instance.

        Raises:
            StorageError: The table does not exist (migrations not applied).
        """
        self._db = db
        self._column_names = db.columns(_TABLE)
        self._columns = ", ".join(self._column_names)
        self._prefixed = ", ".join(f"v.{name}" for name in self._column_names)

    def _to_version(self, row: Sequence[Any]) -> PromptVersion:
        fields = dict(zip(self._column_names, row, strict=True))
        return PromptVersion(
            fields["name"],
            fields["version"],
            fields["content"],
            from_db_time(fields["created_at"]),
            fields["note"],
        )

    def _select_version(
        self, conn: sqlite3.Connection, name: str, version: int
    ) -> PromptVersion:
        row = conn.execute(
            f"SELECT {self._columns} FROM prompt_versions"
            " WHERE name = ? AND version = ?",
            (name, version),
        ).fetchone()
        if row is None:
            raise PromptVersionNotFoundError(
                f"prompt {name!r} has no version {version}"
            )
        return self._to_version(row)

    async def create_version(
        self, name: str, content: str, *, note: str | None = None
    ) -> PromptVersion:
        """Save a new version, numbered after the latest version of `name`."""

        def create() -> PromptVersion:
            now = self._db.now()
            with self._db.write() as conn:
                row = conn.execute(
                    "INSERT INTO prompt_versions"
                    " (name, version, content, note, created_at)"
                    " VALUES (:name,"
                    " (SELECT coalesce(max(version), 0) + 1 FROM prompt_versions"
                    "  WHERE name = :name),"
                    " :content, :note, :now)"
                    f" RETURNING {self._columns}",
                    {"name": name, "content": content, "note": note, "now": now},
                ).fetchone()
                return self._to_version(row)

        return await self._db.run(create)

    async def get_version(self, name: str, version: int) -> PromptVersion:
        """Return one version or raise `PromptVersionNotFoundError`."""
        return await self._db.run(
            lambda: self._select_version(self._db.conn, name, version)
        )

    async def list_versions(self, name: str) -> Sequence[PromptVersion]:
        """Return every version of `name`, oldest first."""

        def list_() -> list[PromptVersion]:
            rows = self._db.conn.execute(
                f"SELECT {self._columns} FROM prompt_versions"
                " WHERE name = ? ORDER BY version",
                (name,),
            ).fetchall()
            return [self._to_version(row) for row in rows]

        return await self._db.run(list_)

    async def find_by_content(self, name: str, content: str) -> PromptVersion | None:
        """Return the latest version of `name` with exactly this content."""

        def find() -> PromptVersion | None:
            row = self._db.conn.execute(
                f"SELECT {self._columns} FROM prompt_versions"
                " WHERE name = ? AND content = ? ORDER BY version DESC LIMIT 1",
                (name, content),
            ).fetchone()
            return None if row is None else self._to_version(row)

        return await self._db.run(find)

    async def get_active(self, name: str) -> PromptVersion:
        """Return the active version or raise `PromptNotFoundError`."""

        def get() -> PromptVersion:
            row = self._db.conn.execute(
                f"SELECT {self._prefixed} FROM active_prompts a"
                " JOIN prompt_versions v USING (name, version)"
                " WHERE a.name = ?",
                (name,),
            ).fetchone()
            if row is None:
                raise PromptNotFoundError(f"prompt {name!r} has no active version")
            return self._to_version(row)

        return await self._db.run(get)

    async def set_active(self, name: str, version: int) -> PromptVersion:
        """Make one version active, or raise `PromptVersionNotFoundError`."""

        def set_() -> PromptVersion:
            with self._db.write() as conn:
                prompt = self._select_version(conn, name, version)
                conn.execute(
                    "INSERT INTO active_prompts (name, version) VALUES (?, ?)"
                    " ON CONFLICT (name) DO UPDATE SET version = excluded.version",
                    (name, version),
                )
                return prompt

        return await self._db.run(set_)

    async def list_active(self) -> Sequence[PromptVersion]:
        """Return the active version of every prompt, ordered by name."""

        def list_() -> list[PromptVersion]:
            rows = self._db.conn.execute(
                f"SELECT {self._prefixed} FROM active_prompts a"
                " JOIN prompt_versions v USING (name, version)"
                " ORDER BY a.name"
            ).fetchall()
            return [self._to_version(row) for row in rows]

        return await self._db.run(list_)


if TYPE_CHECKING:
    from sensai.core.ports import PromptRepository

    # Static check: fails `ty` if this class stops matching the port.
    def _conforms(repo: SqlitePromptRepository) -> PromptRepository:
        return repo
