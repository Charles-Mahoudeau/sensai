# Prompt Versioning

The prompts the team writes, such as Sensai's system prompt, decide how the
model behaves. They are versioned: every version is kept with a timestamp, one
version of each prompt is **active**, and versions can be diffed, rolled back
and compared.

This is not about user messages: conversations are stored by sessions.

## Concepts

| Term | Meaning |
| --- | --- |
| Prompt | A named text, e.g. `system` or `judge` |
| Version | One saved text of a prompt, numbered 1, 2, 3… per prompt, with a timestamp and an optional note |
| Active version | The version Sensai uses; exactly one per prompt |

Prompts in use today:

| Prompt | Used by |
| --- | --- |
| `system` | The chat: sent as the system message, followed by the rendered user profile |
| `judge` | `sensai prompts compare`: judges which of two answers is better |

## Where prompts live

Each prompt has a **default in the code**, `core/prompts/defaults/<name>.md`,
reviewed in pull requests like any other change. The **database** stores every
version and which one is active (`prompt_versions` and `active_prompts`, created
by migration `003_prompts.sql`).

At startup (chat or `sensai prompts …`), `PromptLibrary.sync_defaults()` compares
each default with the stored versions:

- a default whose exact text is **not stored** becomes a new version, noted
  `default from code`, and is **activated**;
- a default that is **already stored** changes nothing.

So editing a default in the code ships it as the next version, while a rollback
to an older version is not undone by the next restart.

## Commands

Run from the repository root (the database is `sensai.db` in the current
directory).

```bash
uv run sensai prompts list                      # every prompt and its active version
uv run sensai prompts history system            # every version, ● marks the active one
uv run sensai prompts show system [VERSION]     # a version's text (active by default)
uv run sensai prompts new system my_prompt.md --note "shorter answers"
uv run sensai prompts diff system 1 2           # unified diff from v1 to v2
uv run sensai prompts rollback system 1         # v1 becomes active again
```

`new` saves the file as a new version and activates it. If the text is identical
to an existing version, that version is re-activated instead of duplicated.

The chat reads the active version when it starts: after `new` or `rollback`,
restart `sensai` to use it.

## Comparison runs

```bash
uv run sensai prompts compare system 1 2 \
    --inputs config/prompt_inputs.txt \
    --model llama3.2:3b --config config/sensai.toml \
    --output report.json
```

Both versions answer every input of the file (one input per line), each used as
the system message. For each version, the report shows:

- mean latency, mean completion tokens and mean answer length;
- **judge wins**: the active `judge` prompt asks the same model which answer is
  better, as JSON (`winner`, `reason`), at temperature 0.

The judge is asked twice per input with the answers swapped. If the two verdicts
disagree, the input counts as a tie, so the position of an answer doesn't decide
the result. `--no-judge` skips this and reports metrics only. `--output` saves
the full report as JSON, including every answer and the judge's reasons.

**Limitation:** a comparison uses the prompt as the system message. That fits
`system` and persona-like prompts. Stage prompts (e.g. the ReAct prompts) need a
harness that runs them in their stage.

## Code

| Zone | File | Role |
| --- | --- | --- |
| Core | `core/models/prompts.py` | `PromptVersion` |
| Core | `core/ports/repositories/prompts.py` | `PromptRepository` port and its errors |
| Core | `core/prompts/defaults.py`, `defaults/*.md` | Default texts, loaded with `importlib.resources` |
| Core | `core/prompts/library.py` | `PromptLibrary`: sync, activate, roll back, diff |
| Core | `core/prompts/comparison.py` | `PromptComparison` and its report |
| Adapter | `adapters/storage/repositories/prompt_repository.py` | `SqlitePromptRepository` |
| Adapter | `adapters/cli/prompts.py` | Terminal output of the commands |
| Wiring | `app.py` | Syncs defaults, builds the system prompt, runs the commands |

## Adding a prompt

1. Add `core/prompts/defaults/<name>.md` with the default text.
2. Read it where it is used through the library, e.g.
   `(await library.active("<name>")).content`, built in `app.py` and passed to
   the component that needs it, instead of a string constant.
3. On the next start, `sync_defaults()` stores it as `<name>` v1.
