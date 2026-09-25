# Database CLI (`scripts/db.py`)

A small command-line tool to manage the local SQLite database and its migrations. It is a thin wrapper around `sensai.adapters.storage.sqlite_migrator` and is meant for developers. For the design behind the database and the migration rules, see [database.md](database.md#7-migrations).

## Running it

The script is `scripts/db.py`. It is not yet registered in `[project.scripts]` of `pyproject.toml` (only `sensai` is), so run it through `uv` from the **repository root**:

```sh
uv sync                                  # once, to install dependencies
uv run python scripts/db.py --help
```

The examples below use `db` as shorthand for `uv run python scripts/db.py`. The parser's program name is `sensai-db`, which is what `--help` prints.

> **Run it from the repository root.** The database path is `DB_FILE = Path("sensai.db")` (`adapters/storage/constants.py`), which is relative to the current working directory. Running the script from another directory creates or targets a different `sensai.db`. The `*.db` files are git-ignored.

## Commands

```
db nuke [-y]
db migrations new <name>
db migrations apply
db migrations status
```

### `nuke`: delete the database

Deletes the `sensai.db` file. It asks `Are you sure you want to nuke the database? (y/N)` and aborts with exit code 1 unless you answer `y`. Pass `-y` / `--yes` to skip the prompt (scripts, CI).

```sh
db nuke        # interactive confirmation
db nuke -y     # no prompt
```

This is irreversible. Only the main file is removed: if the database was in WAL mode, leftover `sensai.db-wal` and `sensai.db-shm` files may remain. Delete them too for a fully clean state. Follow with `migrations apply` to recreate the schema.

### `migrations new <name>`: create a migration file

Creates the next numbered SQL file in `src/sensai/adapters/storage/migrations/` and prints its path.

```sh
db migrations new sessions
# Migration created at .../migrations/0_sessions.sql
```

- Numbering starts at `0` (`MIGRATIONS_START_ID`) and increments from the highest existing id: `0_sessions.sql`, `1_memory.sql`, ...
- The file contains only a comment header. Write your SQLite statements below it.
- The directory is created if it does not exist.

### `migrations apply`: apply pending migrations

Runs every migration file whose id is not yet recorded in the `migrations` table, in id order, then records it. Creates `sensai.db` and the `migrations` table on first use.

```sh
db migrations apply
# Migrations applied
```

- Each migration runs in its own transaction. On any error the migration is rolled back, the error is printed (`Error applying migrations: ...`) and the exit code is 1. Migrations applied before it stay applied.
- Statements are split on `;`, so **do not put a semicolon inside a string literal, a comment or a trigger body** (`CREATE TRIGGER ... BEGIN ...; END;` will not work).
- There is no rollback/down migration.
- It is a no-op when everything is already applied.

### `migrations status`: check whether migrations are up to date

```sh
db migrations status
# Migrations are up to date        (exit code 0)
# Migrations are out of date       (exit code 1)
```

It also validates the history and fails with `Error checking migrations: ...` (exit code 1) if:

- a migration file id is missing (ids must be consecutive from 0: `missing migration file, id: N`), or
- the `migrations` table has a gap (`missing migration in table, id: N`).

Because of the exit codes, it can be used in CI or a pre-start check.

## Typical workflows

**Add a schema change**

```sh
db migrations new add_memory_tables
# edit src/sensai/adapters/storage/migrations/<id>_add_memory_tables.sql
db migrations apply
db migrations status
```

Commit the new `.sql` file with the code that needs it.

**Set up a fresh database**

```sh
db migrations apply
```

**Reset the database during development**

```sh
db nuke -y && db migrations apply
```

**After pulling new migrations from git**

```sh
db migrations apply
```

## Rules and pitfalls

- **Never edit an applied migration.** Add a new one instead.
- **Never delete, skip or renumber migration files.** A gap makes `status` and `apply` fail. Two people creating a migration on separate branches will both get the same id: renumber the later one before merging, and only if it has not been applied anywhere yet.
- **Stale database vs. files.** If `status` says "out of date" right after a fresh checkout, the `migrations` table probably records ids that have no file (for example an old `sensai.db` from another branch). Run `db nuke -y` then `db migrations apply`.
- **Exit codes:** `0` on success; `1` on failure, an aborted `nuke`, or `status` reporting out of date.
- The `migrations` table is `id INTEGER PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP`. The design doc still shows an illustrative `schema_migrations` table with 3-digit ids; the implemented names are the ones above.

## Where the code lives

| Piece | Location |
|---|---|
| CLI (argument parsing, messages, exit codes) | `scripts/db.py` |
| Migration logic (`create_migration`, `apply_migrations`, `check_migrations_state`, `nuke_database`) | `src/sensai/adapters/storage/sqlite_migrator.py` |
| Paths and constants (`DB_FILE`, `MIGRATIONS_DIR`, `MIGRATIONS_START_ID`) | `src/sensai/adapters/storage/constants.py` |
| Connection (WAL, foreign keys, busy timeout) | `src/sensai/adapters/storage/connection.py` |
