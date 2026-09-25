"""Opening a SQLite connection configured the way every store expects."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a connection with the pragmas the schema relies on.

    Transactions are explicit (`BEGIN IMMEDIATE` / `COMMIT`), and the connection
    may be used from worker threads, so its owner must serialize access to it.

    Args:
        path: The database file, or `":memory:"` for a throwaway database.

    Returns:
        The configured connection.
    """
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
