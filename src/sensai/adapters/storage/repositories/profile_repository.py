"""SQLite repository for the persistent user profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.adapters.storage.sqlite import SqliteDatabase, from_db_time
from sensai.core.models.memory import UserProfile
from sensai.core.ports import ProfileNotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

_TABLE = "profiles"


class SqliteProfileRepository:
    """Stores user profile entries in the `profiles` table."""

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

    def _to_profile(self, row: Sequence[Any]) -> UserProfile:
        fields = dict(zip(self._column_names, row, strict=True))
        return UserProfile(
            fields["key"],
            fields["value"],
            fields["category"],
            from_db_time(fields["created_at"]),
            from_db_time(fields["updated_at"]),
        )

    async def set_profile_value(
        self, key: str, value: str, *, category: str | None = None
    ) -> UserProfile:
        """Create or replace an entry.

        A new entry gets the `preference` category when `category` is `None`;
        an existing entry keeps its category.
        """

        def set_() -> UserProfile:
            now = self._db.now()
            with self._db.write() as conn:
                row = conn.execute(
                    "INSERT INTO profiles"
                    " (key, value, category, created_at, updated_at)"
                    " VALUES (:key, :value, coalesce(:category, 'preference'),"
                    " :now, :now)"
                    " ON CONFLICT (key) DO UPDATE SET value = excluded.value,"
                    " category = coalesce(:category, category),"
                    " updated_at = excluded.updated_at"
                    f" RETURNING {self._columns}",
                    {"key": key, "value": value, "category": category, "now": now},
                ).fetchone()
                return self._to_profile(row)

        return await self._db.run(set_)

    async def get_profile(self, key: str) -> UserProfile:
        """Return an entry or raise `ProfileNotFoundError`."""

        def get() -> UserProfile:
            row = self._db.conn.execute(
                f"SELECT {self._columns} FROM profiles WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                raise ProfileNotFoundError(key)
            return self._to_profile(row)

        return await self._db.run(get)

    async def find(self, *, category: str | None = None) -> Sequence[UserProfile]:
        """Return the entries, optionally of one category, ordered by key."""

        def find() -> list[UserProfile]:
            rows = self._db.conn.execute(
                f"SELECT {self._columns} FROM profiles"
                " WHERE (:category IS NULL OR category = :category)"
                " ORDER BY category, key",
                {"category": category},
            ).fetchall()
            return [self._to_profile(row) for row in rows]

        return await self._db.run(find)

    async def delete_profile_value(self, key: str) -> None:
        """Remove an entry; does nothing if the key is unknown."""

        def delete() -> None:
            with self._db.write() as conn:
                conn.execute("DELETE FROM profiles WHERE key = ?", (key,))

        await self._db.run(delete)


if TYPE_CHECKING:
    from sensai.core.ports import UserProfileRepository


    # Static check: fails `ty` if this class stops matching the port.
    def _conforms(repo: SqliteProfileRepository) -> UserProfileRepository:
        return repo
