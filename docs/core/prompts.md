# Prompt Versioning

The prompts the team writes, such as Sensai's system prompt, decide how the
model behaves. They are versioned: every version is kept with a timestamp, one
version of each prompt is **active**, and versions can be diffed, rolled back
and compared.

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
| `react_thought` | ReAct agent: asks for a private thought before acting (`{tools}` is filled in) |
| `react_notes` | ReAct agent: wraps that thought for the acting call (`{thought}` is filled in) |
| `react_answer` | ReAct agent: asks for the final answer after tool results |
| `judge` | `sensai prompts compare`: judges which of two answers is better |

`system` and the `react_*` defaults are the prompts written in the ReAct agent
PR (#106), moved to files unchanged.

## Tutorial

Run every command **from the repository root**: the database is `sensai.db` in
the current directory. Every command first syncs the code defaults into it (see
[Where prompts live](#where-prompts-live)). Help for any command:
`uv run sensai prompts --help`, `uv run sensai prompts compare --help`.

### 1. See what exists

```bash
uv run sensai prompts list
```

```
┃ Prompt        ┃ Active ┃ Versions ┃ Created          ┃ Note              ┃
│ judge         │ v1     │ 1        │ 2026-10-05 21:12 │ default from code │
│ react_answer  │ v1     │ 1        │ …                │ default from code │
│ react_notes   │ v1     │ 1        │ …                │ default from code │
│ react_thought │ v1     │ 1        │ …                │ default from code │
│ system        │ v1     │ 1        │ …                │ default from code │
```

**Active** is the version the chat uses.

### 2. Read a prompt

```bash
uv run sensai prompts show system        # the active version
uv run sensai prompts show system 1      # a specific version
```

### 3. Create a new version

Write the full new text in a file. Start from the current version:

```bash
uv run sensai prompts show system > /tmp/system.md   # then remove the header line and edit
uv run sensai prompts new system /tmp/system.md --note "answer in French by default"
```

```
system v2 is now active
```

The new version becomes active right away. If the text is identical to an
existing version, that version is re-activated instead of duplicated.

`react_thought` and `react_notes` are checked before being saved, and a version
that would break the agent is refused (see [Validation](#validation)):

```
error: prompt 'react_thought' must contain {tools}
```

### 4. Use it in the chat

The chat reads the active versions when it starts:

```bash
uv run sensai --model llama3.2:3b --config config/sensai.toml
```

Restart a chat that was already open to pick up a new version.

### 5. Follow the history and compare texts

```bash
uv run sensai prompts history system     # every version, ● = active
uv run sensai prompts diff system 1 2    # what changed from v1 to v2
```

### 6. Measure which version is better

```bash
uv run sensai prompts compare system 1 2 \
    --inputs config/prompt_inputs.txt \
    --model llama3.2:3b --config config/sensai.toml \
    --output report.json
```

Both versions answer every line of the inputs file (`config/prompt_inputs.txt`
has 5 sample questions). The table shows mean latency, tokens and answer length,
and **judge wins**: which version's answers the model judged better.

- `--no-judge`: metrics only, faster.
- `--output`: saves every answer and the judge's reasons as JSON.

It takes a few minutes: every input runs on both versions, plus the judge. Use
it on `system` for now (see [How a comparison works](#how-a-comparison-works)).

### 7. Go back

```bash
uv run sensai prompts rollback system 1
```

```
system v1 is now active (was v2)
```

The rollback survives restarts. Nothing is deleted, so `rollback system 2`
brings the newer version back.

### Typical workflow

```
show → edit a copy → new (--note why) → chat to try it
     → compare old vs new → keep it, or rollback
```

Versions created with `new` are local experiments: they stay in your
`sensai.db`, aren't shared, and are lost with `scripts/db.py nuke`. To ship a
better prompt to the team, edit its default file instead (next section).

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

So editing a default in the code ships it as the next version on every machine,
while a rollback to an older version is not undone by the next restart.

## Validation

Two prompts are templates the code fills in with `str.format`. A version that
breaks them is refused by `new` (and a broken default fails at startup), with a
message saying what is wrong:

| Prompt | Placeholders (exactly these) | Must contain |
| --- | --- | --- |
| `react_thought` | `{tools}` | `ready to answer` (the phrase `_is_ready()` looks for) |
| `react_notes` | `{thought}` | |

Write literal braces in these two as `{{` and `}}`. The other prompts are sent
as they are, so any text is valid. The rules live in `core/prompts/rules.py`
(`PROMPT_RULES`).

Default files are sent **byte for byte**: `react_notes.md` starts with a newline
and, like `react_answer.md`, has no final newline. The pre-commit whitespace
hooks are disabled for `core/prompts/defaults/` so they don't change them.

## How a comparison works

Each version is sent as the **system message**, followed by one input as the
user message. Latency is measured around each answer, and tokens come from the
model's usage report.

The judge is the active `judge` prompt, asked at temperature 0 to reply in JSON
(`winner`, `reason`). It is asked twice per input with the answers swapped; if
the two verdicts disagree, the input counts as a tie, so the position of an
answer doesn't decide the result. An unreadable verdict also counts as a tie.

**Limitation:** because versions are tested as the system message, this fits
`system` and persona-like prompts. Stage prompts (e.g. the ReAct prompts) need a
harness that runs them in their stage.

## Code

| Zone | File | Role |
| --- | --- | --- |
| Core | `core/models/prompts.py` | `PromptVersion` |
| Core | `core/ports/repositories/prompts.py` | `PromptRepository` port and its errors |
| Core | `core/prompts/defaults.py`, `defaults/*.md` | Default texts, loaded with `importlib.resources` |
| Core | `core/prompts/library.py` | `PromptLibrary`: sync, activate, roll back, diff |
| Core | `core/prompts/rules.py` | `PROMPT_RULES`, `validate`, `InvalidPromptError` |
| Core | `core/agent/prompts.py` | `AgentPrompts`: the ReAct prompts injected into the agent |
| Core | `core/prompts/comparison.py` | `PromptComparison` and its report |
| Adapter | `adapters/storage/repositories/prompt_repository.py` | `SqlitePromptRepository` |
| Adapter | `adapters/cli/prompts.py` | Terminal output of the commands |
| Wiring | `app.py` | Syncs defaults, builds the system prompt, runs the commands |

## Adding a prompt

1. Add `core/prompts/defaults/<name>.md` with the default text, and a name
   constant next to `SYSTEM` in `core/prompts/defaults.py`.
2. Pass the text to the component that uses it instead of a string constant:
   `app.py` reads `(await library.active(<NAME>)).content` and injects it, as it
   does for `AgentPrompts`. Core components don't read the database themselves.
3. If the code fills it in with `str.format`, add a `PromptRule` to
   `PROMPT_RULES` with its placeholders and any phrase the code relies on.
4. On the next start, `sync_defaults()` stores it as `<name>` v1.
