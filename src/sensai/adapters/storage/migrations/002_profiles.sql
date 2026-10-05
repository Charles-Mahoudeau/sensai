create TABLE profiles (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'preference'
        CHECK (category IN ('identity', 'preference', 'instruction', 'other')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;
