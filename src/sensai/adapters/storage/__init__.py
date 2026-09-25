"""SQLite connection setup and the numbered schema migrations."""

from sensai.adapters.storage.sqlite_db import connect
from sensai.adapters.storage.sqlite_migrate import MIGRATIONS, MigrationError, migrate

__all__ = ["MIGRATIONS", "MigrationError", "connect", "migrate"]
