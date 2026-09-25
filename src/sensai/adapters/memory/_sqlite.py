"""Plumbing shared by the SQLite stores: worker thread, transactions, timestamps."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sensai.core.ports import StorageError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _utc_now() -> datetime:
    return datetime.now(UTC)


def to_db_time(moment: datetime) -> str:
    """Format a timestamp as the schema stores it: ISO-8601 UTC, milliseconds."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def from_db_time(text: str) -> datetime:
    """Parse a timestamp written by `to_db_time` or a column default."""
    return datetime.fromisoformat(text)


class SqliteStore:
    """Runs blocking SQLite calls in a worker thread, one at a time."""

    def __init__(
        self, conn: sqlite3.Connection, clock: Callable[[], datetime] | None = None
    ) -> None:
        """Wrap a connection opened by `sensai.adapters.storage.connect`.

        Args:
            conn: The connection, already migrated. Give each store its own.
            clock: Supplies timestamps; the current UTC time by default.
        """
        self._conn = conn
        self._clock = clock or _utc_now
        self._lock = threading.Lock()

    def _now(self) -> str:
        return to_db_time(self._clock())

    async def _run[T](self, operation: Callable[[], T]) -> T:
        """Run `operation` off the event loop, turning SQLite errors into ours."""

        def locked() -> T:
            with self._lock:
                try:
                    return operation()
                except sqlite3.Error as error:
                    raise StorageError(str(error)) from error

        return await asyncio.to_thread(locked)

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """Hold a write transaction, rolled back if the block raises."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
