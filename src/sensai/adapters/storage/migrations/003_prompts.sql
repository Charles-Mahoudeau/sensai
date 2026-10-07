CREATE TABLE prompt_versions (
    name       TEXT    NOT NULL,
    version    INTEGER NOT NULL CHECK (version > 0),
    content    TEXT    NOT NULL,
    note       TEXT,
    created_at TEXT    NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (name, version)
) STRICT;

CREATE TABLE active_prompts (
    name    TEXT    PRIMARY KEY,
    version INTEGER NOT NULL,
    FOREIGN KEY (name, version) REFERENCES prompt_versions (name, version)
) STRICT;
