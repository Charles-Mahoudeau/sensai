# Sensai

## Description

Sensai is a **local maths tutor** for students who get stuck on hard problems. You give it an
exercise (an equation, an integral, a proof, a probability problem…) and it explains how to
approach it, then solves it step by step, showing every intermediate calculation so you can
follow and reproduce the reasoning yourself.

It runs entirely on your machine through [Ollama](https://ollama.com): your questions, your
profile and what Sensai remembers about you never leave your computer, it works offline (except
for the optional web search and GitHub tools), and it costs nothing to use.

## Requirements

* Python 3.14+
* [uv](https://docs.astral.sh/uv/)
* [Ollama](https://ollama.com), running locally (default: `http://localhost:11434`)

## Installation

```bash
uv sync
```

### Ollama model

Installation of Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh   # Linux (macOS/Windows: installer on ollama.com)
ollama list                                     # checks that the Ollama server is running
```

Pick the model according to your hardware:

| Hardware                                    | Model         |
|---------------------------------------------|---------------|
| CPU only, 8–16 GB RAM                       | `llama3.2:3b` |
| GPU 6–8 GB VRAM, or Mac 16 GB (\*)          | `qwen3:8b`    |
| GPU 16 GB+ VRAM, or Mac 32 GB+              | `gpt-oss:20b` |

(\*) `qwen3:8b` also runs on CPU only with 16 GB RAM, but answers are slow.

```bash
ollama pull llama3.2:3b   # or qwen3:8b, or gpt-oss:20b
```

## Usage

Start the chat (a terminal UI):

```bash
uv run sensai --model llama3.2:3b --config config/sensai.toml
```

`--model` and `--config` are both required to start the chat. Then type your problem, for
example:

```text
Solve x² - 5x + 6 = 0 and explain every step.
Compute the integral of x·e^x from 0 to 1 by parts, showing every calculation.
```

The conversation is saved in a local SQLite database (`sensai.db`) and restored the next time
you start Sensai. Type `/clear` to start a new session.

### Slash commands

Type `/` in the prompt to get completions.

| Command               | What it does                                               |
|-----------------------|------------------------------------------------------------|
| `/persona <name>`     | Switch persona (see [Personas](#personas))                 |
| `/effort <level>`     | Change how much the agent reasons (see [ReAct](#react-agent-and-thinking-effort)) |
| `/tools`              | Open a panel to enable or disable each tool                |
| `/mcp`                | List MCP servers and their connection status               |
| `/clear`              | Clear the conversation and start a new session             |
| `/exit` (or `/quit`)  | Quit                                                       |

## Features

### Personas

A persona changes the assistant's role, tone, instructions and output format. Each persona is a
TOML file in `config/personas/`; the one used at start-up is `[personas] default` in the config.

Bundled personas: `sensai`, `prof_francais`, `reviewer`, `vulgarisateur`.

```text
/persona vulgarisateur
Explain what a derivative is.
```

#### Creating a persona

Create a `<name>.toml` file in `config/personas/`; the file name is the persona's name. The
directory is read again on every use, so the new persona appears in `/persona` right away, and
edits to a persona apply the next time it is selected, without restarting.

**Section names are free**: you can put anything in the `[...]`. The bundled personas use
`[identity]`, `[instruction]`, `[tone]`, `[output_format]` and `[response_scope]`, but these are
only conventions. Each section becomes a title in the system message (underscores become
spaces: `[step_by_step]` reads "Step by step:") followed by its entries as `- key: value`
lines, in the order of the file. Keys are free too.

The only rules: every value must be inside a `[section]`, and every value must be a non-empty
string. Otherwise selecting the persona fails with an error naming the file and the faulty key.

```toml
# config/personas/prof_maths.toml
[identity]
name = "Professeur Euler"
role = "A maths teacher who solves hard problems step by step"

[method]
understand = "Restate the problem and identify what is asked before computing anything"
plan = "Explain which method you will use and why it fits"
calculations = "Show every intermediate calculation, never skip a step"
check = "Verify the result (substitute it back, check units or limits)"

[tone]
style = "Patient and rigorous, like a good private tutor"

[output_format]
steps = "Numbered steps, one calculation per line"
result = "End with the final result in bold"
```

```text
/persona prof_maths
```

To start with it by default, set `default = "prof_maths"` in the `[personas]` section of
`config/sensai.toml`.

### User profile

`config/profile.toml` describes who you are and how you want answers (name, level, language,
style…). It is loaded at start-up, stored in `sensai.db` and injected into the system prompt
after the persona, so every answer is adapted to you.

#### Creating a profile

Unlike personas, **the profile sections are fixed**: only these four are accepted, and any
other `[...]` stops Sensai at start-up with an `unknown section` error.

| Section        | Title in the system message | Use it for                         |
|----------------|-----------------------------|------------------------------------|
| `[identity]`   | About the user              | Who you are (name, level, studies) |
| `[preference]` | User preferences            | What you like (language, notation) |
| `[instruction]`| Instructions to follow      | How Sensai must answer             |
| `[other]`      | Other notes                 | Anything else                      |

Keys inside a section are free, and every value must be a non-empty string. A missing file
means an empty profile. Edit the file and restart Sensai to apply the changes.

```toml
# config/profile.toml
[identity]
name = "Tristan"
level = "Third year of a computer science degree"

[preference]
language = "English"
notation = "Use LaTeX-like notation for formulas"

[instruction]
style = "Detail every calculation, do not skip steps"

[other]
weak_points = "Integration by parts and sequences"
```

To use another file, change `path` in the `[profile]` section of `config/sensai.toml`.

### Long-term memory

Sensai remembers facts about you across sessions (your level, what you are studying, what you
struggle with…), stored in `sensai.db`:

* **automatic**: after each message, facts you state about yourself are extracted and saved, and
  relevant memories are recalled into the context of the next turns;
* **tools**: the model can also manage memories explicitly with `memory_create`, `memory_read`,
  `memory_update` and `memory_delete`.

```text
Remember that I'm in my last year of high school and that I struggle with sequences.
What do you know about me?
Forget that I'm in high school, I'm now in my first year of university.
```

Disabling the memory tools in `/tools` also stops the automatic memory writes.

### Tools

| Tool                    | What it does                                                   |
|-------------------------|----------------------------------------------------------------|
| `web_search`            | Searches the web (DuckDuckGo) and returns the top results      |
| `memory_*`              | Create, read, update and delete long-term memories             |
| GitHub tools (MCP)      | The tools exposed by the GitHub MCP server, if `GITHUB_TOKEN` is set |

```text
Search the web for the proof of Fermat's Last Theorem and summarize it.
```

* `/tools` toggles each tool on or off while the chat runs.
* `uv run sensai --model qwen3:8b --config config/sensai.toml --no-tools` starts with every tool
  disabled (they can be re-enabled from `/tools`).
* `/mcp` shows whether the GitHub MCP server is connected, and why not otherwise.

### ReAct agent and thinking effort

Each answer is produced by a ReAct loop: the agent thinks, calls tools if needed, observes the
results, and repeats until it can answer. Its reasoning steps and tool calls are shown in the
TUI. The *thinking effort* caps the number of think/act cycles per turn:

| Level    | Max cycles |
|----------|------------|
| `none`   | 0          |
| `low`    | 2          |
| `medium` | 5          |
| `high`   | 12         |
| `ultra`  | 30         |

Set the default with `[agent] thinking_effort`, or change it live:

```text
/effort high
```

### Prompt versioning

Every prompt Sensai sends to the model is versioned: each version is stored in `sensai.db` with
a number, a timestamp and an optional note, and exactly one version per prompt is active. You
can tune how the tutor explains (e.g. ask for more detailed calculations), measure whether the
new version is better, and roll back if it is not.

Versioned prompts:

| Prompt              | Used by                                                        |
|---------------------|----------------------------------------------------------------|
| `system`            | The chat's system message, followed by the user profile        |
| `react_thought`     | ReAct agent: private thought before acting                     |
| `react_notes`       | ReAct agent: passes that thought to the acting call            |
| `react_answer`      | ReAct agent: final answer after tool results                   |
| `memory_extraction` | Memory: extracts the facts to save / forget from a message     |
| `memory_recall`     | Memory: title above the recalled memories                      |
| `judge`             | `prompts compare`: judges which of two answers is better       |

Commands (`uv run sensai prompts <command>`):

| Command                                   | What it does                                       |
|-------------------------------------------|----------------------------------------------------|
| `list`                                    | List every prompt and its active version           |
| `history <name>`                          | List every version of a prompt (● = active)        |
| `show <name> [version]`                   | Print a version (the active one by default)        |
| `new <name> <file> [--note TEXT]`         | Save a file as the new active version              |
| `diff <name> <old> <new>`                 | Show the changes between two versions              |
| `rollback <name> <version>`               | Make an older version active again                 |
| `compare <name> <a> <b> --inputs FILE --model M --config C [--no-judge] [--output FILE]` | Run two versions on the same inputs and compare them |

Example: make the tutor detail every calculation, then check that it helps.

```bash
uv run sensai prompts list
uv run sensai prompts show system > my_system.md
# edit my_system.md, e.g. add "Show every intermediate calculation."
uv run sensai prompts new system my_system.md --note "detail every calculation"
uv run sensai prompts diff system 1 2
uv run sensai prompts compare system 1 2 \
  --inputs config/prompt_inputs.txt \
  --model qwen3:8b --config config/sensai.toml \
  --output report.json
uv run sensai prompts rollback system 1     # if v2 is worse
```

* `compare` sends each version as the system message for every line of the inputs file, and
  shows the mean latency, tokens and answer length of each version, plus **judge wins**: an LLM
  judge (the `judge` prompt) picks the better answer, asked twice with the answers swapped to
  avoid position bias. `--no-judge` only computes the metrics; `--output` saves every answer and
  the judge's reasons as JSON.
* `new` refuses a version that breaks a template (e.g. `react_thought` must keep its `{tools}`
  placeholder), with a message saying what is wrong.
* The chat reads the active versions at start-up: restart it to use a new version.
* Rollbacks survive restarts and nothing is deleted, so `rollback system 2` brings the newer
  version back.

Details: [docs/core/prompts.md](docs/core/prompts.md).

## Configuration

The config file is passed with `--config` (`config/sensai.toml` by default in the examples).
Paths in it are relative to the repository root.

```toml
[ollama]
url = "http://localhost:11434"   # where Ollama listens

[profile]
path = "config/profile.toml"     # the user profile

[personas]
path = "config/personas"         # one TOML file per persona
default = "sensai"               # persona at start-up; remove it to use the base prompt

[agent]
thinking_effort = "medium"       # none | low | medium | high | ultra
```

The model is chosen on the command line with `--model`.

### Turning features off

| Feature              | How to disable it                                              |
|----------------------|----------------------------------------------------------------|
| All tools            | `--no-tools` at start-up, or `/tools` in the chat              |
| One tool             | `/tools`, then toggle it                                       |
| Long-term memory     | Disable the `memory_*` tools in `/tools`                       |
| GitHub MCP server    | Leave `GITHUB_TOKEN` unset                                     |
| ReAct reasoning      | `thinking_effort = "none"` or `/effort none`                   |
| Persona              | Remove `default` from `[personas]`                             |

### Environment variables

| Variable       | Purpose                                                                     |
|----------------|-----------------------------------------------------------------------------|
| `GITHUB_TOKEN` | GitHub token for the GitHub MCP server. **Without it the server is skipped** (a warning is written to `sensai.log` and `/mcp` shows no server). |

Secrets are never read from the TOML file. Put them in your environment or in a `.env` file at
the repository root (loaded automatically):

```bash
echo 'GITHUB_TOKEN=ghp_...' > .env
```

Logs are written to `sensai.log`.

## Checking that it works

Run the test suite (it uses fake LLM and MCP clients, so Ollama is not needed):

```bash
uv run pytest
```

Run the tests of one feature:

```bash
uv run pytest tests/adapters/persona tests/core/test_persona.py   # personas
uv run pytest tests/adapters/memory tests/core/tools               # memory and tools
uv run pytest tests/adapters/mcp                                   # MCP client
uv run pytest tests/core/agent                                     # ReAct agent and memory
uv run pytest tests/core/prompts tests/adapters/cli                # versioned prompts
```

To evaluate a prompt change against a real model, use
[`sensai prompts compare`](#prompt-versioning) with `config/prompt_inputs.txt`.

## Documentation

* Project structure and conventions: [docs/structure.md](docs/structure.md)
* Architecture: [engine](docs/core/engine.md), [agent](docs/core/agent.md),
  [models](docs/core/models.md), [ports](docs/core/ports.md), [prompts](docs/core/prompts.md),
  [TUI](docs/adapters/tui.md)
* Database: [design](docs/database.md), [schema](docs/database_schema.md),
  [CLI](docs/database_cli.md)
* User stories: [prompt versioning](docs/user-stories/a4-prompt-versioning.md),
  [tools and MCP commands](docs/user-stories/tools-and-mcp-commands.md)

## Development

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
uv run ty check        # type check
uv run pytest          # run tests
```

### SQL formatting

Format all SQL files with the project-specific continuation indentation:

```bash
uv run python scripts/format_sql.py
```

Check the formatting without modifying files:

```bash
uv run python scripts/format_sql.py --check
```

Run SQLFluff's remaining SQL checks:

```bash
uv run sqlfluff lint .
```

### Pre-commit hooks

This repo uses [pre-commit](https://pre-commit.com/) to run lint, format, and type checks
before each commit, and the test suite before each push. Install the hooks once after cloning:

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

To run all hooks manually against the full codebase:

```bash
uv run pre-commit run --all-files
uv run pre-commit run --all-files --hook-stage pre-push
```

## Authors

* Charles Mahoudeau - ``charles.mahoudeau@epitech.eu``
* Matthieu Coraleau - ``matthieu.coraleau@epitech.eu``
* Noé Caillaud - ``noe.caillaud@epitech.eu``
* Tristan Fragnaud - ``tristan.fragnaud@epitech.eu``
