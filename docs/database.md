# Sensai: Database & Persistence

> **Note: code is illustrative.** All code names (classes, functions, files, folders, tables, ports), all code snippets, and everything else code-related in this document are **examples**. They show the intended design and are **not required**. They may differ from the final code. The technical choices (SQLite with sqlite-vec and FTS5, WAL, no ORM, repositories, numbered migrations) are the part that is decided.

This document explains what Sensai stores, which database we chose, why, and how the persistence code is organized. It is meant as onboarding documentation and as the justification of our technical choices.

**TL;DR**

- One embedded **SQLite** database (WAL mode) with two extensions: **sqlite-vec** (vector search) and **FTS5** (keyword search).
- A second, separate SQLite file for logs and metrics.
- Configuration (personas, prompts, settings) lives in **YAML/TOML files** versioned in git.
- **No ORM.** Plain `sqlite3` with hand-written SQL, wrapped in **repositories**.
- Repositories are **adapters** implementing **ports** (`typing.Protocol`) defined in the application layer (hexagonal architecture).
- Schema changes go through **numbered SQL migrations**.

---

## 1. What we need to store

| Data | Feature | Shape and access pattern |
|---|---|---|
| Sessions, messages, tool calls | M1, X2 | Relational, append-heavy. Branching (X2) makes messages a tree (`parent_id`). |
| User profile, preferences | M1 | Tiny key-value/JSON, read at every init. |
| Structured memory (facts, entities, relations) | M3 | Relational CRUD, driven by the LLM through tool calls. |
| RAG chunks, embeddings, metadata | R1, R2 | Vectors + metadata filtering (date, source, author) + keyword search for hybrid retrieval. |
| Semantic cache | A6 | Query embedding + response, similarity threshold, TTL, invalidation. |
| Logs and metrics | EV3 | Write-heavy, then aggregations (latency, error rate, tokens per day). |
| Persona and prompt versions | A4, A5 | Human-edited config, versioned and diffable. |
| Artifacts / state documents | M4 | Text + version history. |
| Permissions, scheduled jobs | T4, X5 | Small tables. |
| Event queue | Architecture §5 | In memory (`asyncio.Queue`). Not a database concern. |

Three of these need **vector similarity** (RAG, cache, optionally memory search). Everything else is ordinary relational or document data.

## 2. Options considered

| Option | Chat & memory (CRUD) | Vectors | Metadata filtering | Logs & metrics | Setup | Verdict |
|---|---|---|---|---|---|---|
| **SQLite + sqlite-vec + FTS5** | Excellent | Good (brute-force, fine up to ~100k–500k chunks) | Excellent (plain SQL) | Good | No server, one file | **Chosen** |
| PostgreSQL + pgvector | Excellent | Excellent (HNSW) | Excellent | Excellent | Server or Docker | Overkill for a local app |
| ChromaDB | Poor | Good | Basic | No | Easy | RAG only; adds a second system |
| LanceDB | Fair | Very good (ANN, disk-based) | Good | Fair | Easy | Strong alternative if we outgrow sqlite-vec |
| Qdrant | No | Excellent | Excellent | No | Server or Docker | Overkill, RAG only |
| FAISS / hnswlib | No | Fast | None | No | Easy | Libraries, not databases: we would rebuild metadata and persistence |
| DuckDB | Weak (many small writes) | Experimental vss extension | Good | Excellent | Easy | Only useful for the dashboard |
| Redis Stack | Fair | Good | Good | Fair | Server, memory-bound | Reasonable for the cache only |
| MongoDB | Good | Limited locally | Fair | Fair | Server | No advantage here |
| YAML/TOML/JSON files | n/a | n/a | n/a | n/a | Trivial | Right for config only |

## 3. Decision and rationale

**One SQLite database plus config files.**

1. **The data is mostly relational.** Sessions, messages, memory and permissions are plain tables. A vector-only database would leave us with a second system for everything else.
2. **Vector needs are modest.** A local assistant over personal or project documents means thousands to low hundreds of thousands of chunks, which brute-force search handles.
3. **No server to run.** Ollama is already local. One file is easy to demo, back up and reset before a keynote.
4. **`sqlite3` is in the standard library.** It respects the project rule (no LLM framework, standard utilities are fine) and adds nothing to justify.
5. **Transactions across concerns.** Messages, memory and cache live in the same database, so they can be written atomically.
6. **SQL filtering makes R2 trivial.** Metadata filtering is a `WHERE` clause; hybrid retrieval combines vector and FTS5 in one engine.

### Layout of the data

- **`sensai.db`** (SQLite, WAL mode):
  - `sessions`, `messages` (with `parent_id`), `tool_calls`, `profiles`
  - `memory_facts`, `memory_entities`, `memory_relations`, `memory_audit` (M3)
  - `chunks` (text + metadata), `vec_chunks_<model><dim>` (sqlite-vec), `fts_chunks` (FTS5)
  - `cache_entries` (embedding, response, persona/model key, created_at, TTL)
  - `artifacts`, `artifact_versions`, `schedules`, `permissions`
- **`logs.db`**: separate SQLite file for events and metrics. Its write pattern (constant appends) is different, and a separate file avoids lock contention with the main database. It is accessed through the `LogSink` port.
- **`config/`**: personas, prompts and settings as YAML/TOML, versioned in git. Prompt versioning (A4) can store timestamped copies and eval scores in the database.
- **Event queue**: in memory.

## 4. Extensions

### sqlite-vec (vector search)

- Provides `vec0` virtual tables for similarity search.
- **Brute-force, no ANN index.** Fast enough for thousands to low hundreds of thousands of chunks; it will not scale to millions.
- **Young project.** As far as we know it is still pre-1.0 and its API has been changing. **Pin the exact version** in `requirements.txt` and check the release notes before relying on newer features (metadata columns, partition keys).
- **Must be loaded on every connection** (`enable_load_extension`).
- **Not `sqlite-vss`**: it is the older, deprecated predecessor.

### FTS5 (keyword search / BM25)

- Built into most SQLite builds. Check `PRAGMA compile_options` at startup and fail with a clear message if it is missing.
- Used with an **external-content table plus triggers**, so `chunks` stays the single source of truth and text is never indexed twice.
- **Hybrid retrieval:** run vector and BM25 searches separately, then merge with **Reciprocal Rank Fusion** (`score = Σ 1/(k + rank)`, k ≈ 60). It needs no score normalization.

### Fallback: numpy vector search

Extension loading can fail (macOS system Python, some locked-down machines). Fallback:

- Vectors stored as `float32` BLOBs in a normal table, similarity computed with `numpy`.
- Slower but fine for a few thousand chunks.
- Implemented as a **second adapter** of the same `ChunkStore` port (`NumpyChunkStore`), selected in `bootstrap.py` at startup. No `if` inside a single class.

### Vector rules

- **Normalize embeddings at write time** and use cosine/dot product consistently, for chunks and cache alike.
- **One vec table per (model, dimension)**, for example `vec_chunks_nomic768`, since `vec0` fixes the dimension at creation. Switching embedding models means a new table and a re-index. Store the model name with each vector.
- Embeddings come from Ollama's `/api/embed`, called directly.

## 5. Repositories, and why there is no ORM

### Decision: no ORM, repositories with hand-written SQL

- **An ORM** maps rows to objects and generates SQL (SQLAlchemy ORM, Peewee, Django ORM).
- **The repository pattern** is a code organization: all the SQL for one kind of data sits behind a small class, and the rest of the app calls methods like `messages.branch(leaf_id)` without knowing SQL exists.

We use the second without the first. Each repository is a plain class taking a connection, containing hand-written parameterized SQL, and returning dataclasses. In hexagonal terms, each repository is an **adapter implementing a port**.

### Why not an ORM

1. **The hardest tables are not ORM-shaped.** `vec0` (sqlite-vec) and FTS5 are virtual tables with their own syntax (`MATCH`, `ORDER BY distance`, `bm25()`). ORMs cannot model them, so we would write raw SQL for the core of RAG and the cache anyway, and end up with two access styles in one codebase.
2. **Extension loading.** sqlite-vec must be loaded on every connection. With raw `sqlite3` it is a few lines; with an ORM it means hooking connection events.
3. **Branching needs recursive CTEs.** The active branch of a conversation is a `WITH RECURSIVE` walk up `parent_id`. The SQL is clearer written by hand.
4. **LLM-driven CRUD (M3) needs control.** The model emits tool calls such as `update_fact(id, ...)`. We want to control exactly which SQL runs, validate arguments first, and log and permission-gate each call. One explicit method per tool is easier to reason about than ORM session behavior.
5. **Footprint and clarity.** `sqlite3` is in the standard library: nothing to install, nothing to justify against the "no framework" spirit of the project.

### When we would reconsider

- The schema grows to 20+ related entities with many joins.
- We need several database backends.
- The team prefers an ORM for speed.

In that case we would use **SQLAlchemy Core** or **Peewee**, keeping virtual tables in raw SQL.

### Repository conventions

- A repository is a plain class (or a module of functions if it has two queries). No abstract base classes: the **ports** are the interfaces.
- Every statement is parameterized (`?` / `:name`), including FTS `MATCH` input (sanitize or quote it; FTS has its own query syntax).
- Row → dataclass mapping lives in one helper, not in every repository.
- Ports never expose `sqlite3.Row`, `Connection` or FTS5 query strings.
- Writes use `BEGIN IMMEDIATE`. If several stores must write atomically, add a `UnitOfWork` port only when a real need appears.

Example: active branch of a conversation.

```python
BRANCH_SQL = """
WITH RECURSIVE branch(id, parent_id, role, content, depth) AS (
    SELECT id, parent_id, role, content, 0 FROM messages WHERE id = :leaf
    UNION ALL
    SELECT m.id, m.parent_id, m.role, m.content, b.depth + 1
    FROM messages m JOIN branch b ON m.id = b.parent_id
)
SELECT * FROM branch ORDER BY depth DESC;
"""

class SqliteMessageStore:  # implements the MessageStore port
    def __init__(self, conn): self.conn = conn

    def branch(self, leaf_id: int) -> list[Message]:
        rows = self.conn.execute(BRANCH_SQL, {"leaf": leaf_id}).fetchall()
        return [to_message(r) for r in rows]
```

## 6. Connection setup

```python
# adapters/storage/sqlite_db.py
import sqlite3, sqlite_vec

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)  # explicit transactions
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
```

If `enable_load_extension` fails, `bootstrap.py` selects the numpy fallback adapter.

### WAL mode (Write-Ahead Logging)

**What it is.** WAL is an alternative to SQLite's default rollback-journal mode.

- **Default mode:** before changing a page, SQLite copies the original page into a `-journal` file, then writes the change directly into the main database file. While a write is in progress, readers are blocked.
- **WAL mode:** the main file is left untouched during a write. Changes are appended to a separate `-wal` file. Readers see a consistent snapshot made of the main file plus the relevant part of the WAL. A **checkpoint** later copies the WAL content back into the main file (automatic by default, when the WAL reaches about 1000 pages).

Two extra files appear next to the database, `sensai.db-wal` and `sensai.db-shm` (shared-memory index of the WAL). They are normal and belong to the database.

**Why we use it.**

1. **Readers and the writer don't block each other.** The TUI or Web API can read messages, RAG chunks or the cache while another task writes a message, a log batch or a memory fact. In default mode this causes "database is locked" errors or stalls.
2. **Faster writes.** Appending to a log is cheaper than copy-then-overwrite, and with `synchronous = NORMAL` it needs fewer disk syncs. This matters for constant small writes (messages, events).
3. **Still crash-safe.** Committed transactions are in the WAL and are replayed on the next open. With `synchronous = NORMAL`, the last transactions may be lost on a power failure or OS crash (not on an application crash), but the database is not corrupted. This is acceptable for chat history. Use `synchronous = FULL` if every commit must survive power loss.
4. **The mode is persistent.** It is stored in the database file. `connect()` sets it on every connection anyway, which is harmless.

**What it does not change.** There is still **one writer at a time**. WAL lets readers run alongside that writer, but two writers still queue. This is why we use a single writer task, `BEGIN IMMEDIATE` and a `busy_timeout` (see section 11).

**Caveats.**

- **Local filesystems only.** WAL relies on shared memory and is not reliable on network filesystems (NFS, SMB). Keep `sensai.db` on a local disk.
- **Backups must account for the WAL.** Copying only `sensai.db` while the app runs can give an incomplete or stale copy. Use `conn.backup()` or `VACUUM INTO`, or run `PRAGMA wal_checkpoint(TRUNCATE)` and then copy. Never mix a `.db` file with `-wal`/`-shm` files from another moment.
- **Long-lived readers delay checkpoints.** A read transaction held open for a long time prevents the WAL from being reset, so it grows. Keep read transactions short.
- **Repository hygiene.** Add `*.db`, `*.db-wal` and `*.db-shm` to `.gitignore`, and don't ship the WAL files with the seeded demo database. Produce a clean single-file snapshot with `conn.backup()`.

## 7. Migrations

Schema changes are **numbered SQL files** applied in order. The applied version is stored in `PRAGMA user_version`. No Alembic: the runner is small and enough for this project.

```
adapters/storage/migrations/
├── 001_core.sql     # sessions, messages, tool_calls, profiles
├── 002_rag.sql      # chunks, vec_chunks_*, fts_chunks (+ triggers)
└── 003_cache.sql    # cache_entries
```

```python
# adapters/storage/sqlite_migrate.py
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"

def migrate(conn, folder: Path = MIGRATIONS) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for f in sorted(folder.glob("*.sql")):
        version = int(f.name.split("_")[0])
        if version <= current:
            continue
        try:
            conn.executescript(
                f"BEGIN; {f.read_text()}\n; PRAGMA user_version = {version};"
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
```

Rules:

- **Never edit an applied migration.** Add a new numbered file.
- The connection must come from `connect()` first: `vec0` and FTS5 migrations need the extension loaded.
- Test migrations from an empty database in CI.

## 8. Schema conventions

- **`STRICT` tables** (SQLite 3.37+) so wrong types fail loudly.
- Timestamps as **UTC ISO-8601 text** or integer epoch, never local time.
- `ON DELETE CASCADE` where appropriate (session → messages → tool_calls). Index every foreign key we query by (`parent_id`, `session_id`).
- Embeddings normalized at write time; model name stored with each vector.

## 9. Safety of LLM-driven CRUD (M3)

- **The model never writes SQL.** It picks a tool and arguments; the repository runs a fixed, parameterized statement.
- **Whitelist** the fields each tool can touch, and validate arguments (type, length, allowed values) before the repository call.
- **Soft deletes** (`deleted_at`) on memory facts, plus a `memory_audit` table (what changed, when, previous value). This supports the human-in-the-loop story (A3) and lets us undo a bad model edit.
- **Stored memory is untrusted text.** A fact saved from a web page or document can carry a prompt injection into later sessions. This belongs in the adversarial test suite (EV4).

## 10. Semantic cache correctness

Cache entries are keyed on `(persona, model, profile hash)` in addition to the embedding, and are invalidated when RAG documents are re-ingested. Otherwise a cached answer from another persona or from stale documents would be served.

## 11. Concurrency

- SQLite allows a single writer. The TUI, Web API and Logger all consume the event queue, so writes go through **one writer task** (or WAL with short transactions). Readers use their own connections.
- `logs.db` is written through the `LogSink` port with **batched inserts** (every N events or every second) and a **retention policy** so it does not grow without bound.

## 12. Operations

- DB path is **configurable** (`SENSAI_DB` or a config key), so tests and demos use separate files.
- A **seeded demo database** (or seed script) ships with pre-ingested documents and a sample profile, so slow embedding steps are never run live.
- Snapshots with `conn.backup()` or `VACUUM INTO` before a demo.
- **Privacy:** the database can contain conversations and PII. If we build EV2, decide whether anonymization happens before or after storage. **SQLCipher** was considered and ruled out (extra build complexity, out of scope).

## 13. Testing

- Application tests run against **in-memory fakes** (`InMemoryChunkStore`, `FakeChatModel`), so the agent loop is testable without Ollama or SQLite.
- SQLite adapter tests use `:memory:` plus the **real migrations**, so schema and code cannot drift.
- One **contract test suite per port**, run against every adapter (real and fake).
- **Retrieval golden test:** a small fixed corpus with expected top-k results, to catch regressions when chunking or the embedding model changes.
- Test the branch CTE with a forked conversation, and the cache key (a different persona or model must miss).

## 14. Known limits

- sqlite-vec is brute-force: it does not scale to millions of chunks. If we outgrow it, only the vectors move to LanceDB or Qdrant, behind the same `ChunkStore` port.
- sqlite-vec is young; the version is pinned and its API may change.
- Single writer: heavy concurrent writes need the writer-task pattern.
- If heavier analytics are needed for the EV3 dashboard, DuckDB can read the SQLite logs directly. We do not expect to need it.
