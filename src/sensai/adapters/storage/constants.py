"""Constants for the storage adapter."""

from pathlib import Path

DB_FILE: str = "sensai.db"
MIGRATIONS_DIR: Path = Path(__file__).parent.joinpath("migrations")
MIGRATIONS_START_ID: int = 0
