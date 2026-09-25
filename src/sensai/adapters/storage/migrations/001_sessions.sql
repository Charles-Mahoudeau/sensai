CREATE TABLE sessions (
    id             INTEGER PRIMARY KEY,
    title          TEXT,
    model          TEXT    NOT NULL,
    mode           TEXT    NOT NULL DEFAULT 'execute'
                           CHECK (mode IN ('plan', 'execute')),
    thinking       INTEGER NOT NULL DEFAULT 0 CHECK (thinking IN (0, 1)),
    tool_exec_mode TEXT    NOT NULL DEFAULT 'ask'
                           CHECK (tool_exec_mode IN ('ask', 'auto')),
    token_budget   INTEGER,
    created_at     TEXT    NOT NULL
                           DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at     TEXT    NOT NULL
                           DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE messages (
    id                INTEGER PRIMARY KEY,
    session_id        INTEGER NOT NULL
                              REFERENCES sessions (id) ON DELETE CASCADE,
    parent_id         INTEGER REFERENCES messages (id) ON DELETE SET NULL,
    role              TEXT    NOT NULL
                              CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content           TEXT    NOT NULL DEFAULT '',
    thinking          TEXT,
    tool_calls_json   TEXT    CHECK (json_valid(tool_calls_json)),
    tool_name         TEXT,
    status            TEXT    NOT NULL DEFAULT 'complete'
                              CHECK (status IN ('streaming', 'complete', 'interrupted',
                                                'error', 'cached')),
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    created_at        TEXT    NOT NULL
                              DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE INDEX messages_session_id_id ON messages (session_id, id);
CREATE INDEX messages_parent_id ON messages (parent_id);

CREATE TABLE user_profile (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'preference'
                    CHECK (category IN ('identity', 'preference', 'instruction', 'other')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;
