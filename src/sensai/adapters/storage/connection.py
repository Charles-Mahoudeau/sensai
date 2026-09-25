"""Connection to an SQLite database."""

import sqlite3

from sensai.adapters.storage import DB_FILE


def create_connection() -> sqlite3.Connection:
    """Creates a database connection.

    Returns:
        A SQLite connection object.
    """
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn
