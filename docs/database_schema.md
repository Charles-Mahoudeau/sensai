# Sensai — Database Schema (SQLite)

> **Extensions / prerequisites**
> - **`sqlite-vec` (optional)**: provides `vec0` virtual tables for fast KNN search over embeddings (RAG + semantic cache). **Without it**, embeddings are stored as `BLOB` (float32, little-endian) and cosine similarity is computed in Python. The schema works in both modes (see [section 12](#12-optional-tables-with-extensions)).
> - **FTS5** (built into most CPython SQLite builds): optional, only for keyword search over RAG chunks (hybrid retrieval).
> - **JSON1**: built-in. JSON is stored as `TEXT`.
> - **Encryption (`mcp_secrets`)**: done in Python (e.g. the `cryptography` package for AES-GCM/scrypt), not in SQLite. No SQLCipher or DB extension needed.
> - Pragmas to set on every connection: `PRAGMA foreign_keys = ON;` and `PRAGMA journal_mode = WAL;`

## Conventions

| Topic | Rule |
|---|---|
| Types | Only SQLite storage classes: `INTEGER`, `TEXT`, `REAL`, `BLOB` |
| Primary keys | `INTEGER PRIMARY KEY` (rowid alias) unless stated otherwise |
| Timestamps | `TEXT`, ISO-8601 UTC, default `strftime('%Y-%m-%dT%H:%M:%fZ','now')` |
| Booleans | `INTEGER`, `CHECK (col IN (0,1))` |
| JSON | `TEXT` holding a JSON document (`CHECK (json_valid(col))`) |
| Enums | `TEXT` + `CHECK (col IN (...))`; allowed values listed in the Notes column |
| Deletes | Everything a session owns is `ON DELETE CASCADE` from `sessions` |
| `FK →` | Foreign key, written `table.column` (with the delete rule when not the default) |

---

## 1. Data inventory (what must be stored, per feature)

| Feature | Data to persist | Tables |
|---|---|---|
| **Base / settings** | Selected model, toggles (semantic cache, tool exec mode, fs permissions), thresholds | `app_settings`, `schema_migrations` |
| **M1** Session persistence & profiles | Sessions, messages, user profile (preferences, custom instructions) | `sessions`, `messages`, `user_profile` |
| **M2** Token budgeting & compression | Per-turn token counts, budget, summary blocks replacing old turns | `messages` (token cols), `sessions.token_budget`, `session_summaries` |
| **M3** External structured memory | Entities, facts, relationships | `memory_entities`, `memory_facts`, `memory_relations` |
| **M4** Artifact & state document | Living documents + version history of applied edits | `artifacts`, `artifact_versions` |
| **T1** MCP | MCP server configs, encrypted credentials per auth method, every tool call (args, result, approval) | `mcp_servers`, `mcp_secrets`, `tool_calls` |
| **T2** Sandboxed exec | Code run, stdout/stderr, exit code | `tool_calls` |
| **T3** Web search | Query + results | `tool_calls` |
| **T4** File access | Directory grants (scope remembered per session) | `fs_permissions` |
| **T5** Structured output | Nothing extra (validated JSON lands in `messages` / `tool_calls`) | none |
| **R1/R2** RAG | Documents, chunks, embeddings, metadata | `rag_documents`, `rag_chunks` (+ optional vec/FTS) |
| **A1** ReAct | Reasoning trace per message; each loop step = LLM call + tool call | `messages.thinking`, `llm_calls`, `tool_calls` |
| **A2** Multi-agent / subagents | Agent definitions, nested run tree | `agent_definitions`, `agent_runs` |
| **A3** Human-in-the-loop | Plans, plan steps, approval state of tool calls | `plans`, `plan_steps`, `tool_calls.approval_status` |
| **A4** Prompt versioning | Versioned prompts, active version | `prompt_versions` |
| **A5** Persona | Persona profiles, switchable mid-session | `personas`, `sessions.persona_id` |
| **A6** Semantic cache | Query, embedding, cached response, hit stats | `semantic_cache` |
| **A7** Prompt optimization | Few-shot example pool; raw vs optimized prompt per request | `few_shot_examples`, `llm_calls` |
| **EV1** Auto eval / hallucination | Judge scores, flagged claims, runs comparable across versions | `eval_runs`, `eval_results` |
| **EV2** Guardrails | Configurable rules, every trigger (block / anonymize / injection) | `guardrail_rules`, `guardrail_events` |
| **EV3** Logging & monitoring | Every LLM call (latency, tokens, errors) + event log | `llm_calls`, `events` |
| **EV4** Adversarial testing | Attack cases + outcomes | `eval_cases`, `eval_runs`, `eval_results` |
| **X2** Branching / interrupt | Message tree, active branch tip, interrupted status | `messages.parent_id`, `sessions.active_message_id`, `messages.status` |
| **X3** Export & publication | Public share tokens + frozen snapshot | `shared_links` |
| **X4** Questions & forms | Questions asked by the LLM, form schema, user answers | `user_questions` |
| **X5** Scheduling | Recurring tasks and their runs | `scheduled_tasks`, `scheduled_runs` |

---

## 2. Core

### `schema_migrations`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `version` | INTEGER | PRIMARY KEY | Migration number |
| `applied_at` | TEXT | NOT NULL, DEFAULT now | |

### `app_settings`

Key/value settings: `default_model`, `semantic_cache_enabled`, `semantic_cache_threshold`, `tool_exec_mode_default`, `fs_permissions_enabled`, `rag_top_k`, `default_token_budget`…

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `key` | TEXT | PRIMARY KEY | |
| `value` | TEXT | NOT NULL | JSON-encoded scalar |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

---

## 3. Memory & context (M1, M2, A5, X2)

### `user_profile` (M1)

Persistent profile, auto-injected at session init.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `key` | TEXT | PRIMARY KEY | `name`, `language`, `custom_instructions`… |
| `value` | TEXT | NOT NULL | |
| `category` | TEXT | NOT NULL, DEFAULT `'preference'` | `identity` \| `preference` \| `instruction` \| `other` |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

### `personas` (A5)

Personas are data, not code.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL, UNIQUE | e.g. `sensei-ja`, `legal-assistant` |
| `role` | TEXT | NOT NULL | |
| `tone` | TEXT | | |
| `scope` | TEXT | | What it should / should not answer |
| `system_prompt` | TEXT | NOT NULL | |
| `model` | TEXT | | Optional per-persona model override |
| `options_json` | TEXT | JSON | temperature, top_p, num_ctx… |
| `is_default` | INTEGER | NOT NULL, DEFAULT 0 | Boolean |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

### `sessions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `title` | TEXT | | |
| `model` | TEXT | NOT NULL | Ollama model name |
| `persona_id` | INTEGER | FK → `personas.id` ON DELETE SET NULL | Switchable mid-session, history untouched |
| `mode` | TEXT | NOT NULL, DEFAULT `'execute'` | `plan` \| `execute` |
| `thinking` | INTEGER | NOT NULL, DEFAULT 0 | Boolean: ReAct on/off |
| `tool_exec_mode` | TEXT | NOT NULL, DEFAULT `'ask'` | `ask` \| `auto` |
| `token_budget` | INTEGER | | M2: max context tokens for this session |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

### `messages`

X2: messages form a tree. A branch is the path from a leaf up to the root through `parent_id`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `parent_id` | INTEGER | FK → `messages.id` ON DELETE SET NULL | NULL = root message |
| `role` | TEXT | NOT NULL | `system` \| `user` \| `assistant` \| `tool` |
| `content` | TEXT | NOT NULL, DEFAULT `''` | |
| `thinking` | TEXT | | A1: reasoning trace, kept apart from the answer |
| `tool_calls_json` | TEXT | JSON | Assistant tool requests (Ollama format) |
| `tool_name` | TEXT | | Only for `role = 'tool'` |
| `persona_id` | INTEGER | FK → `personas.id` ON DELETE SET NULL | Persona active when produced |
| `status` | TEXT | NOT NULL, DEFAULT `'complete'` | `streaming` \| `complete` \| `interrupted` \| `error` \| `cached` |
| `prompt_tokens` | INTEGER | | M2: Ollama `prompt_eval_count` |
| `completion_tokens` | INTEGER | | Ollama `eval_count` |
| `summary_id` | INTEGER | FK → `session_summaries.id` ON DELETE SET NULL  | Replaced by a summary id if it's a summary block |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(session_id, id)`, `(parent_id)`

### `session_summaries` (M2)

Summary blocks standing in for a range of old turns.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `from_message_id` | INTEGER | NOT NULL, FK → `messages.id` ON DELETE CASCADE | Start of summarized range |
| `to_message_id` | INTEGER | NOT NULL, FK → `messages.id` ON DELETE CASCADE | End of summarized range |
| `content` | TEXT | NOT NULL | |
| `token_count` | INTEGER | | Size of the summary |
| `tokens_saved` | INTEGER | | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(session_id)`

---

## 4. External structured memory (M3) & artifacts (M4)

### `memories` (M3)

Long-term, cross-session memory driven by the agent through CRUD tool calls.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL | |
| `type` | TEXT | NOT NULL | `person`, `project`, `concept`, `vocab`… |
| `description` | TEXT | | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

Constraints: `UNIQUE (name, type)`

### `artifacts` (M4)

Living deliverable, distinct from the chat transcript.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `title` | TEXT | NOT NULL | |
| `format` | TEXT | NOT NULL, DEFAULT `'markdown'` | `markdown` \| `json` \| `text` \| `code` |
| `current_version` | INTEGER | NOT NULL, DEFAULT 1, FK → `artifact_versions.id` ON DELETE SET NULL | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

### `artifact_versions` (M4)

Full snapshot per version, plus the parseable edit that produced it (rollback and audit).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `artifact_id` | INTEGER | NOT NULL, FK → `artifacts.id` ON DELETE CASCADE | |
| `version` | INTEGER | NOT NULL | |
| `content` | TEXT | NOT NULL | Full document at this version |
| `edit_json` | TEXT | JSON | `{section, op, text}` emitted by the model |
| `message_id` | INTEGER | FK → `messages.id` ON DELETE SET NULL | Message that triggered the edit |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Constraints: `UNIQUE (artifact_id, version)`

---

## 5. Tools, MCP, permissions, agents (T1 to T4, A2)

### `mcp_servers` (T1)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL, UNIQUE | |
| `transport` | TEXT | NOT NULL | `http` |
| `url` | TEXT | | http only |
| `auth_method` | TEXT | NOT NULL, DEFAULT `'none'` | `none` \| `api_key` \| `bearer` \| `basic` \| `oauth2` \| `custom` |
| `enabled` | INTEGER | NOT NULL, DEFAULT 1 | Boolean |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

### `mcp_secrets` (T1)

Credentials for MCP servers, **encrypted at rest**. One row per secret, so one server can hold several (e.g. OAuth access token + refresh token + client secret). The plaintext never touches the DB, and the encryption key is never stored: only *where it comes from* (`key_source` / `key_ref`) is recorded.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `server_id` | INTEGER | NOT NULL, FK → `mcp_servers.id` ON DELETE CASCADE | |
| `name` | TEXT | NOT NULL | Logical name: `API_KEY`, `access_token`, `refresh_token`, `client_secret`, `username`, `password`… |
| `auth_type` | TEXT | NOT NULL | `api_key` \| `bearer` \| `basic_username` \| `basic_password` \| `oauth_access_token` \| `oauth_refresh_token` \| `oauth_client_secret` \| `custom` |
| `ciphertext` | BLOB | NOT NULL | Encrypted secret |
| `expires_at` | TEXT | | OAuth token expiry, to trigger a refresh |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |
| `rotated_at` | TEXT | | Last re-encryption or token refresh |

Constraints: `UNIQUE (server_id, name)`. Indexes: `(server_id)`

Implementation notes:

- **Decrypt at the last moment:** only when spawning the MCP server (env/args) or building the HTTP request (headers). Never put plaintext in `messages`, `tool_calls`, `llm_calls` or `events`, and never in the prompt sent to the model.

### `agent_definitions` (A2)

Subagent definitions (nested loop, scoped tools).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL, UNIQUE | |
| `description` | TEXT | NOT NULL | Shown to the caller as the tool description |
| `system_prompt` | TEXT | NOT NULL | |
| `model` | TEXT | | |
| `allowed_tools_json` | TEXT | NOT NULL, DEFAULT `'[]'`, JSON | Tool scope for the permission layer |
| `max_iterations` | INTEGER | NOT NULL, DEFAULT 8 | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

### `agent_runs` (A1, A2)

Tree of loop executions: one root run per user turn, children are subagents.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `parent_run_id` | INTEGER | FK → `agent_runs.id` ON DELETE CASCADE | NULL = root run |
| `agent_id` | INTEGER | FK → `agent_definitions.id` ON DELETE SET NULL | NULL = main agent |
| `kind` | TEXT | NOT NULL, DEFAULT `'execute'` | `plan` \| `execute` \| `subagent` |
| `task` | TEXT | | |
| `result` | TEXT | | |
| `status` | TEXT | NOT NULL, DEFAULT `'running'` | `running` \| `done` \| `error` \| `cancelled` |
| `iterations` | INTEGER | NOT NULL, DEFAULT 0 | Loop steps used |
| `started_at` | TEXT | NOT NULL, DEFAULT now | |
| `ended_at` | TEXT | | |

Indexes: `(session_id)`, `(parent_run_id)`

### `tool_calls` (T1 to T4, A3)

Every tool invocation: native, MCP, sandbox, web search, filesystem, memory CRUD, subagent.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `run_id` | INTEGER | FK → `agent_runs.id` ON DELETE CASCADE | |
| `message_id` | INTEGER | FK → `messages.id` ON DELETE SET NULL | |
| `tool_name` | TEXT | NOT NULL | |
| `source` | TEXT | NOT NULL, DEFAULT `'native'` | `native` \| `mcp` \| `subagent` |
| `mcp_server_id` | INTEGER | FK → `mcp_servers.id` ON DELETE SET NULL | Only when `source = 'mcp'` |
| `arguments_json` | TEXT | NOT NULL, DEFAULT `'{}'`, JSON | |
| `result` | TEXT | | stdout, file content, search results (truncate large payloads) |
| `is_error` | INTEGER | NOT NULL, DEFAULT 0 | Boolean |
| `approval_status` | TEXT | NOT NULL, DEFAULT `'auto'` | `auto` \| `pending` \| `approved` \| `denied` \| `blocked` (blocked = permission layer) |
| `duration_ms` | INTEGER | | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(session_id, id)`, `(tool_name)`

### `fs_permissions` (T4)

Per-directory consent. `session_id` NULL means a persistent grant. The `.aiignore` file lives on disk, not in the DB.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | FK → `sessions.id` ON DELETE CASCADE | NULL = persistent |
| `path` | TEXT | NOT NULL | Absolute, normalized directory path |
| `access` | TEXT | NOT NULL, DEFAULT `'read'` | `read` \| `write` \| `read_write` |
| `granted_at` | TEXT | NOT NULL, DEFAULT now | |

Constraints: `UNIQUE (session_id, path)`

---

## 6. Plan mode & questions (A3, X4)

### `plans` (A3)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `run_id` | INTEGER | FK → `agent_runs.id` ON DELETE SET NULL | |
| `goal` | TEXT | NOT NULL | |
| `revision` | INTEGER | NOT NULL, DEFAULT 1 | Incremented on each "request changes" |
| `status` | TEXT | NOT NULL, DEFAULT `'draft'` | `draft` \| `accepted` \| `changes_requested` \| `running` \| `done` \| `failed` |
| `feedback` | TEXT | | User feedback that triggered the next revision |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

### `plan_steps` (A3)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `plan_id` | INTEGER | NOT NULL, FK → `plans.id` ON DELETE CASCADE | |
| `position` | INTEGER | NOT NULL | Order in the plan |
| `description` | TEXT | NOT NULL | |
| `status` | TEXT | NOT NULL, DEFAULT `'pending'` | `pending` \| `done` \| `skipped` \| `deviated` |
| `outcome` | TEXT | | Track/report: what actually happened vs the plan |

Constraints: `UNIQUE (plan_id, position)`

### `user_questions` (X4)

Questions asked by the LLM through the `ask_user_question` tool.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | NOT NULL, FK → `sessions.id` ON DELETE CASCADE | |
| `tool_call_id` | INTEGER | FK → `tool_calls.id` ON DELETE SET NULL | |
| `question` | TEXT | NOT NULL | |
| `form_json` | TEXT | JSON | Options / field schema |
| `answer_json` | TEXT | JSON | |
| `status` | TEXT | NOT NULL, DEFAULT `'pending'` | `pending` \| `answered` \| `skipped` |
| `asked_at` | TEXT | NOT NULL, DEFAULT now | |
| `answered_at` | TEXT | | |

---

## 7. RAG (R1, R2) & semantic cache (A6)

### `rag_documents`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `source_path` | TEXT | NOT NULL | |
| `title` | TEXT | | |
| `mime_type` | TEXT | | |
| `sha256` | TEXT | NOT NULL, UNIQUE | Skip re-ingestion of unchanged files |
| `author` | TEXT | | R2: metadata filter |
| `doc_date` | TEXT | | R2: ISO date, metadata filter |
| `category` | TEXT | | R2: metadata filter |
| `ingested_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(category, doc_date, author)`

### `rag_chunks`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `document_id` | INTEGER | NOT NULL, FK → `rag_documents.id` ON DELETE CASCADE | |
| `chunk_index` | INTEGER | NOT NULL | Position in the document |
| `content` | TEXT | NOT NULL | |
| `token_count` | INTEGER | | |
| `start_offset` | INTEGER | | Character offset in the source |
| `end_offset` | INTEGER | | |
| `embedding` | BLOB | NOT NULL | float32[`embedding_dim`] |
| `embedding_model` | TEXT | NOT NULL | e.g. `nomic-embed-text`. Re-embed if it changes |
| `embedding_dim` | INTEGER | NOT NULL | |

Constraints: `UNIQUE (document_id, chunk_index)`. Indexes: `(document_id)`

### `semantic_cache` (A6)

A cache hit skips the model entirely. A response is only valid for the same persona, model and prompt version.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `query_text` | TEXT | NOT NULL | |
| `query_embedding` | BLOB | NOT NULL | float32 vector |
| `embedding_model` | TEXT | NOT NULL | |
| `response` | TEXT | NOT NULL | |
| `persona_id` | INTEGER | FK → `personas.id` ON DELETE CASCADE | Part of the cache key |
| `model` | TEXT | NOT NULL | Part of the cache key |
| `prompt_version_id` | INTEGER | FK → `prompt_versions.id` ON DELETE CASCADE | Part of the cache key |
| `hit_count` | INTEGER | NOT NULL, DEFAULT 0 | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `last_hit_at` | TEXT | | |
| `expires_at` | TEXT | | |

Indexes: `(persona_id, model)`

---

## 8. Prompts & few-shot (A4, A7)

### `prompt_versions` (A4)

Every prompt (persona system prompt, optimizer, guardrail, judge) is versioned.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL | `system.sensei`, `stage.optimizer`, `stage.guardrail`, `judge.faithfulness`… |
| `version` | INTEGER | NOT NULL | |
| `content` | TEXT | NOT NULL | |
| `is_active` | INTEGER | NOT NULL, DEFAULT 0 | Boolean |
| `notes` | TEXT | | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Constraints: `UNIQUE (name, version)`. Partial unique index `(name) WHERE is_active = 1` guarantees at most one active version per name.

> `prompt_versions` must be created before `semantic_cache` and `llm_calls` in the migration order.

### `few_shot_examples` (A7)

Pool of examples selected by embedding similarity for dynamic few-shot prompting.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `task` | TEXT | NOT NULL | Which prompt/stage the example serves |
| `input` | TEXT | NOT NULL | |
| `output` | TEXT | NOT NULL | |
| `embedding` | BLOB | | |
| `embedding_model` | TEXT | | |
| `score` | REAL | | Quality signal used for selection |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(task)`

---

## 9. Guardrails & evaluation (EV1, EV2, EV4)

### `guardrail_rules` (EV2)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL, UNIQUE | |
| `direction` | TEXT | NOT NULL | `input` \| `output` |
| `kind` | TEXT | NOT NULL | `pii` \| `regex` \| `topic` \| `llm` |
| `config_json` | TEXT | NOT NULL, JSON | Pattern, entity types, allowed topics… |
| `action` | TEXT | NOT NULL | `block` \| `anonymize` \| `refuse` \| `flag` |
| `enabled` | INTEGER | NOT NULL, DEFAULT 1 | Boolean |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

### `guardrail_events` (EV2)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | FK → `sessions.id` ON DELETE CASCADE | |
| `message_id` | INTEGER | FK → `messages.id` ON DELETE SET NULL | |
| `rule_id` | INTEGER | FK → `guardrail_rules.id` ON DELETE SET NULL | NULL for the injection tripwire (no `send_result` call) |
| `direction` | TEXT | NOT NULL | `input` \| `output` |
| `outcome` | TEXT | NOT NULL | `passed` \| `blocked` \| `anonymized` \| `refused` \| `flagged` \| `injection_suspected` |
| `detail` | TEXT | | What matched. Store masked values, never raw PII |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(session_id)`

### `eval_cases` (EV1, EV4)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `suite` | TEXT | NOT NULL | `quality` \| `rag` \| `adversarial` |
| `category` | TEXT | | `jailbreak`, `prompt_injection`, `malformed`, `grammar`… |
| `input` | TEXT | NOT NULL | |
| `expected` | TEXT | | Reference answer or expected behavior (`refuse`, `no tool call`) |
| `context` | TEXT | | Source text for faithfulness checks |
| `metadata_json` | TEXT | JSON | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

### `eval_runs` (EV1, EV4)

One run = one system configuration measured against a suite, so versions can be compared.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `label` | TEXT | NOT NULL | `baseline`, `optimizer-v2`… |
| `suite` | TEXT | NOT NULL | |
| `model` | TEXT | NOT NULL | |
| `judge_model` | TEXT | | |
| `persona_id` | INTEGER | FK → `personas.id` ON DELETE SET NULL | |
| `config_json` | TEXT | JSON | Toggles, active `prompt_versions` ids |
| `started_at` | TEXT | NOT NULL, DEFAULT now | |
| `finished_at` | TEXT | | |
| `summary_json` | TEXT | JSON | Averages, pass rate |

### `eval_results` (EV1, EV4)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `run_id` | INTEGER | NOT NULL, FK → `eval_runs.id` ON DELETE CASCADE | |
| `case_id` | INTEGER | FK → `eval_cases.id` ON DELETE SET NULL | NULL for live-scored messages |
| `message_id` | INTEGER | FK → `messages.id` ON DELETE SET NULL | |
| `response` | TEXT | | |
| `relevance` | REAL | | Between 0 and 1 |
| `coherence` | REAL | | Between 0 and 1 |
| `faithfulness` | REAL | | Between 0 and 1 |
| `flagged_claims_json` | TEXT | JSON | Unverifiable or source-contradicted statements |
| `passed` | INTEGER | | Boolean. Adversarial: 1 = the system held |
| `latency_ms` | INTEGER | | |
| `notes` | TEXT | | |

Indexes: `(run_id)`

---

## 10. Observability (EV3)

### `llm_calls`

One row per call to the Ollama HTTP API (main loop, optimizer/guardrail stage, summarizer, judge, embeddings).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | FK → `sessions.id` ON DELETE CASCADE | |
| `run_id` | INTEGER | FK → `agent_runs.id` ON DELETE SET NULL | |
| `message_id` | INTEGER | FK → `messages.id` ON DELETE SET NULL | |
| `stage` | TEXT | NOT NULL | `optimizer` \| `guardrail` \| `embedding` \| `rag_rerank` \| `plan` \| `execute` \| `subagent` \| `summary` \| `judge` \| `other` |
| `endpoint` | TEXT | NOT NULL | `/api/chat`, `/api/embed`… |
| `model` | TEXT | NOT NULL | |
| `prompt_version_id` | INTEGER | FK → `prompt_versions.id` ON DELETE SET NULL | |
| `original_prompt` | TEXT | | A7: raw user prompt before optimization |
| `request_json` | TEXT | | Prompt sent |
| `response_text` | TEXT | | |
| `prompt_tokens` | INTEGER | | |
| `completion_tokens` | INTEGER | | |
| `latency_ms` | INTEGER | | |
| `ttft_ms` | INTEGER | | Time to first token |
| `cache_hit` | INTEGER | NOT NULL, DEFAULT 0 | Boolean |
| `error` | TEXT | | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(created_at)`, `(stage, model)`

### `events`

Persisted event-queue traffic for the Logger consumer. Do not persist every `token_generated` event (too many rows); aggregate them into `llm_calls`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `session_id` | INTEGER | FK → `sessions.id` ON DELETE CASCADE | |
| `run_id` | INTEGER | FK → `agent_runs.id` ON DELETE SET NULL | |
| `type` | TEXT | NOT NULL | `message_started`, `message_completed`, `tool_call`, `tool_result`, `plan_updated`, `mode_changed`, `error`, `done` |
| `payload_json` | TEXT | NOT NULL, DEFAULT `'{}'`, JSON | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

Indexes: `(session_id, id)`, `(type, created_at)`

### `v_llm_metrics` (view)

Derived from `llm_calls`, grouped by `day, stage, model, prompt_version_id`.

| Column | Type | Definition |
|---|---|---|
| `day` | TEXT | `date(created_at)` |
| `stage` | TEXT | |
| `model` | TEXT | |
| `prompt_version_id` | INTEGER | |
| `calls` | INTEGER | `COUNT(*)` |
| `avg_latency_ms` | REAL | `AVG(latency_ms)` |
| `avg_ttft_ms` | REAL | `AVG(ttft_ms)` |
| `total_tokens` | INTEGER | `SUM(prompt_tokens + completion_tokens)` |
| `error_rate` | REAL | `AVG(error IS NOT NULL)` |
| `cache_hit_rate` | REAL | `AVG(cache_hit)` |

---

## 11. Export, sharing, scheduling (X3, X5)

### `shared_links` (X3)

Public no-auth link. A frozen snapshot keeps the shared page stable. Exports (JSON / Markdown / PDF) are generated on demand, so nothing is stored for them.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `token` | TEXT | PRIMARY KEY | Random URL-safe string (`secrets.token_urlsafe`) |
| `kind` | TEXT | NOT NULL | `conversation` \| `artifact` |
| `session_id` | INTEGER | FK → `sessions.id` ON DELETE CASCADE | Required when `kind = 'conversation'` |
| `artifact_id` | INTEGER | FK → `artifacts.id` ON DELETE CASCADE | Required when `kind = 'artifact'` |
| `title` | TEXT | | |
| `snapshot` | TEXT | NOT NULL | Rendered Markdown/JSON at share time |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `expires_at` | TEXT | | |
| `revoked` | INTEGER | NOT NULL, DEFAULT 0 | Boolean |

Constraints: `CHECK` that the id matching `kind` is not NULL.

### `scheduled_tasks` (X5)

Entry point "scheduled trigger".

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `name` | TEXT | NOT NULL, UNIQUE | |
| `prompt` | TEXT | NOT NULL | |
| `schedule` | TEXT | NOT NULL | Cron expression or interval (`every 1h`) |
| `persona_id` | INTEGER | FK → `personas.id` ON DELETE SET NULL | |
| `model` | TEXT | | |
| `tool_exec_mode` | TEXT | NOT NULL, DEFAULT `'auto'` | `ask` \| `auto` |
| `enabled` | INTEGER | NOT NULL, DEFAULT 1 | Boolean |
| `last_run_at` | TEXT | | |
| `next_run_at` | TEXT | | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

### `scheduled_runs` (X5)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY | |
| `task_id` | INTEGER | NOT NULL, FK → `scheduled_tasks.id` ON DELETE CASCADE | |
| `session_id` | INTEGER | FK → `sessions.id` ON DELETE SET NULL | Each run produces a session |
| `status` | TEXT | NOT NULL, DEFAULT `'running'` | `running` \| `done` \| `error` |
| `error` | TEXT | | |
| `started_at` | TEXT | NOT NULL, DEFAULT now | |
| `ended_at` | TEXT | | |

Indexes: `(task_id, started_at)`

---

## 12. Optional tables (with extensions)

Virtual tables; `rowid` mirrors the id of the source table. Dimension must match the embedding model (768 shown for `nomic-embed-text`).

| Table | Module | Columns / options | Mirrors |
|---|---|---|---|
| `vec_rag_chunks` | `sqlite-vec` `vec0` | `embedding float[768] distance_metric=cosine` | `rag_chunks.id` |
| `vec_semantic_cache` | `sqlite-vec` `vec0` | `embedding float[768] distance_metric=cosine` | `semantic_cache.id` |
| `rag_chunks_fts` | FTS5 | `content`, external content `rag_chunks`, `content_rowid = id` | `rag_chunks.id` |

---

## 13. Relationships at a glance

| From | Relation | To |
|---|---|---|
| `sessions` | 1 → N | `messages`, `session_summaries`, `agent_runs`, `plans`, `fs_permissions`, `user_questions`, `guardrail_events`, `events`, `artifacts`, `tool_calls`, `llm_calls` |
| `sessions` | N → 1 | `personas` |
| `messages` | tree (`parent_id`) | `messages` |
| `agent_runs` | tree (`parent_run_id`) | `agent_runs` |
| `agent_runs` | 1 → N | `tool_calls`, `llm_calls` |
| `plans` | 1 → N | `plan_steps` |
| `artifacts` | 1 → N | `artifact_versions` |
| `memory_entities` | 1 → N | `memory_facts` |
| `memory_entities` | N ↔ N via `memory_relations` | `memory_entities` |
| `rag_documents` | 1 → N | `rag_chunks` |
| `prompt_versions` | 1 → N | `llm_calls`, `semantic_cache` |
| `eval_runs` | 1 → N | `eval_results` |
| `eval_cases` | 1 → N | `eval_results` |
| `scheduled_tasks` | 1 → N | `scheduled_runs` |
| `mcp_servers` | 1 → N | `tool_calls`, `mcp_secrets` |
| `shared_links` | N → 1 | `sessions` or `artifacts` |

## 14. Design notes

- **Not stored in the DB on purpose:** `.aiignore` (file on disk), exports (generated on demand), structured-output JSON (validated in memory, persisted through `messages` / `tool_calls`), the Ollama model list (queried live).
- **Global vs per-session data:** `user_profile`, `memory_*`, `rag_*`, `semantic_cache`, `personas`, `prompt_versions` are global. Everything else hangs off a session and cascades on delete.
- **Repository pattern (no ORM):** one repository per aggregate, e.g. `SessionRepository` (sessions, messages, summaries), `MemoryRepository`, `ArtifactRepository`, `RagRepository`, `CacheRepository`, `ToolCallRepository`, `PlanRepository`, `PromptRepository`, `EvalRepository`, `ObservabilityRepository`, `SchedulerRepository`, `ShareRepository`, `SettingsRepository`.
- **Secrets and logs:** `mcp_secrets` is the only place credentials are persisted, and only encrypted. `tool_calls.arguments_json`, `tool_calls.result`, `llm_calls.request_json` and `events.payload_json` must be redacted before insert (mask any value that came from `mcp_secrets`), otherwise the logging tables would leak what the encryption protects.
- **Per-feature migrations:** tables for optional features (M3, M4, RAG, cache, eval, scheduling…) can be created lazily, so only the features actually implemented ship their tables.
- **Embedding dimension** depends on the model: `embedding_model` / `embedding_dim` are stored so vectors can be re-embedded when the model changes.
