# Verification

How to check that each feature works, how to run the checks again, and where their results are
kept. The acceptance criteria behind each check are in the [user stories](../user-stories/README.md).

## Four kinds of checks

| Kind | What it proves | Command | Results kept in |
|---|---|---|---|
| Automated tests | The code behaves as specified, with fake models and fake MCP servers: no Ollama or network needed | `uv run pytest -v -rs` | `reports/tests/<date>-pytest.txt` |
| Live tests | The adapters work against the real services | `SENSAI_LIVE_OLLAMA=1 uv run pytest -v tests/adapters/ollama/test_live.py` (model: `SENSAI_LIVE_MODEL`, default `llama3.2:3b`)<br>`SENSAI_LIVE_SANDBOX=1 uv run pytest -v tests/adapters/sandbox/test_live.py` (needs Docker and the `sensai-sandbox` image) | `reports/tests/<date>-pytest-live-<service>.txt` |
| Manual checks | The feature works end to end in the chat, with a real model | The prompts in [Manual checks](#manual-checks) below | `reports/manual/<date>-<name>.md` |
| Model benchmark | The model answers maths questions correctly, at what speed and memory | `uv run python scripts/benchmark.py` ([method](../benchmark.md)) | `benchmarks/results/<date>_<time>-<machine>/` |

To save a run, redirect its output into the matching file:

```bash
uv run pytest -v -rs > reports/tests/$(date +%F)-pytest.txt 2>&1
SENSAI_LIVE_OLLAMA=1 uv run pytest -v tests/adapters/ollama/test_live.py \
  > reports/tests/$(date +%F)-pytest-live-ollama.txt 2>&1
```

For manual checks, copy the checklist of the features you test into
`reports/manual/<date>-<name>.md`, tick each line that passes, and write down what happened for each
line that fails. Note the model used (`--model`) at the top.

### Latest results

| Check | Date | Result |
|---|---|---|
| Automated tests | 2026-11-01 | 582 passed, 15 skipped (the live tests) ([report](../../reports/tests/2026-11-01-pytest.txt)) |
| Live tests, Ollama | 2026-11-01 | 3 passed with `llama3.2:3b` ([report](../../reports/tests/2026-11-01-pytest-live-ollama.txt)) |
| Live tests, sandbox | Not run | The `sensai-sandbox` image is not built on the test machine |
| Model benchmark | 2026-10-31 | 3 models, 14 questions ([report](../../benchmarks/results/2026-10-31_2337-matthieu-laptop/report.md)) |
| Manual checks | Not run yet | |

## Automated tests per feature

| Feature | Tests |
|---|---|
| [B1] Base chatbot | `tests/core/test_engine.py`, `tests/adapters/ollama/`, `tests/adapters/tui/test_chat_app.py`, `tests/adapters/tui/test_latex.py`, `tests/adapters/tui/widgets/test_math_markdown.py`, `tests/test_cli.py`, `tests/test_config.py` |
| [M1] Sessions and profile | `tests/core/test_sessions.py`, `tests/adapters/storage/repositories/test_session_repository.py`, `tests/adapters/profile/` |
| [M3] Structured memory | `tests/core/agent/test_memory_extraction.py`, `tests/core/agent/test_memory_recall.py`, `tests/core/agent/test_memory_tools.py`, `tests/core/tools/builtin/test_memory.py`, `tests/adapters/storage/repositories/test_memory_repository.py` |
| [A1] ReAct | `tests/core/agent/test_re_act.py`, `tests/core/agent/test_step.py`, `tests/core/agent/test_thought_stream.py` |
| [A4] Prompt versioning | `tests/core/prompts/`, `tests/adapters/cli/`, `tests/adapters/storage/repositories/test_prompt_repository.py` |
| [A5] Personas | `tests/core/test_persona.py`, `tests/adapters/persona/` |
| [T1] MCP and tools | `tests/adapters/mcp/`, `tests/core/tools/test_mcp.py`, `tests/core/tools/builtin/test_calculator.py`, `tests/core/tools/test_registry.py`, `tests/adapters/tui/commands/test_builtin.py` |
| [T2] Python sandbox | `tests/core/tools/builtin/test_python.py`, `tests/adapters/sandbox/` |
| [T3] Web search | None for the tool itself; the call loop is covered by `tests/core/agent/test_re_act.py` |
| [EV3] Logging (partial) | `tests/adapters/tui/panels/test_logs.py`, `tests/adapters/tui/test_log_buffer.py`, `tests/adapters/tui/test_log_format.py` |
| [T5] Structured output | `tests/core/agent/test_step.py`, `tests/core/agent/test_structured.py`, `tests/core/agent/structured/`, `tests/core/prompts/test_comparison.py` |

Run one feature's tests by passing its paths, for example
`uv run pytest tests/core/agent/test_re_act.py tests/core/agent/test_step.py`.

## Manual checks

Start the chat with `uv run sensai --model qwen2.5:7b --config config/sensai.toml`. Lines marked
**negative** check that a bad input or a failure is handled: Sensai must report it and keep running,
never crash or make up a result.

### [B1] Base chatbot

- [ ] « Résous x² − 5x + 6 = 0 » → the answer appears piece by piece, not in one block.
- [ ] « Pourquoi tu calcules le discriminant ? » → the answer is about the same equation, which was
  not repeated.
- [ ] `Esc` during an answer → the answer stops and `(interrupted)` is shown.
- [ ] **Negative**: send an empty message → `Type a message and press Enter. /exit to quit.`, nothing
  is sent to the model.
- [ ] **Negative**: stop Ollama, send a message → `cannot reach Ollama at …` in the chat, Sensai stays
  open; start Ollama again, the next message is answered.
- [ ] **Negative**: start with `--model does-not-exist` and send a message → Ollama's "not found"
  error is shown, Sensai stays open.

### [M1] Sessions and profile

- [ ] Send a message, `/exit`, start again → the last conversation is shown.
- [ ] `/sessions` → the sessions are listed with a title, most recent first; choosing one shows its
  messages.
- [ ] `/clear` → a new session starts; the previous one is still in `/sessions`.
- [ ] Set `style = "Réponds en français et détaille chaque calcul"` under `[instruction]` in
  `config/profile.toml`, restart, ask in English → the answer is in French with every calculation.
- [ ] **Negative**: add a `[hobbies]` section to `config/profile.toml` → Sensai refuses to start with
  `unknown section [hobbies]`.

### [M3] Structured memory

- [ ] « J'ai beaucoup de mal avec les raisonnements par récurrence » → a `memory_create` call appears
  after the answer; `sqlite3 sensai.db "SELECT name, type, description FROM memories"` shows it.
- [ ] `/clear`, then « Qu'est-ce que tu sais de moi ? » → the answer mentions induction.
- [ ] « Oublie ce que tu sais sur mes difficultés » → a `memory_delete` call appears and the row is
  gone from `memories`.
- [ ] **Negative**: « Combien font 12 × 7 ? » → no memory call, `memories` does not change.
- [ ] **Negative**: disable the `memory_*` tools in `/tools`, then « J'ai du mal avec les
  probabilités » → no memory call, `memories` does not change.

### [A1] ReAct

- [ ] With `/effort medium`, ask an exercise → a reasoning block (thoughts, then tool calls) comes
  before the answer.
- [ ] `/effort none`, same exercise → the answer comes directly, without a reasoning block.
- [ ] **Negative**: `/effort extreme` → `Unknown effort 'extreme'. Use one of: …`, the level does not
  change.
- [ ] **Negative**: see [T3](#t3-web-search), a failing tool still ends with an answer.

### [A4] Prompt versioning

- [ ] `uv run sensai prompts list` → every prompt and its active version.
- [ ] `uv run sensai prompts show system > my.md`, edit it, `uv run sensai prompts new system my.md
  --note "test"` → `prompts history system` shows the new version as active (`●`).
- [ ] `uv run sensai prompts diff system 1 2` → the changed lines.
- [ ] `uv run sensai prompts rollback system 1` → version 1 is active again.
- [ ] **Negative**: save a `react_thought` version without its `{tools}` placeholder → refused with a
  message saying what is missing, no version created.

### [A5] Personas

- [ ] `/persona` → the active persona and the list of available ones.
- [ ] Solve an exercise, `/persona vulgarisateur`, « Réexplique l'étape 2 plus simplement » → a
  simpler explanation of step 2 of the same exercise.
- [ ] **Negative**: `/persona does-not-exist` → an error, the active persona does not change.

### [T1] MCP and tools

- [ ] Run `uv run python scripts/fake_mcp_server.py`, start Sensai, `/mcp` → the `fake` server is
  connected with its tool count.
- [ ] « Utilise l'outil echo pour répéter "bonjour" » → a `fake__echo` call with its result; the
  server prints the request.
- [ ] « Combien font (12,5 × 4)² / √16 ? » → a `calculator` call; the answer gives 625, the value
  the tool returned.
- [ ] **Negative**: « Calcule 1 / 0 avec la calculatrice » → the `calculator` call is shown as failed
  (`ZeroDivisionError`), and the answer says the division is impossible.
- [ ] `/tools`, disable `web_search` → the counts update; « Cherche sur internet la correction de cet
  exercice » triggers no `web_search` call.
- [ ] **Negative**: start Sensai without the fake server → Sensai starts, `/mcp` shows the `fake`
  server as failed, with the reason.

### [T2] Python sandbox

Needs Docker and `docker build -t sensai-sandbox src/sensai/adapters/sandbox/image`.

- [ ] « Calcule l'intégrale de x·eˣ entre 0 et 1 » → a `run_python` call; the answer gives 1, the
  value the script printed.
- [ ] « Trace f(x) = x·e⁻ˣ sur [0 ; 5] » → the figure is shown, and saved under `artifacts/`.
- [ ] **Negative**: « Exécute une boucle infinie en Python » → the run is stopped at the time limit,
  and Sensai says so.
- [ ] **Negative**: stop Docker and start Sensai → Sensai starts without `run_python`, and
  `sensai.log` says why, with the `docker build` command.

### [T3] Web search

Depends on the network: keep a recording for the defense.

- [ ] « Quelle est la date de l'épreuve de spécialité maths du bac cette année ? » → a `web_search`
  call with its results; the answer gives at least one URL from them.
- [ ] **Negative**: cut the network (Ollama still running), same question → the `web_search` call is
  shown as failed; the answer says the search failed and gives no made-up date or URL.

### [T5] Structured output

- [ ] Ask an exercise, then open `/logs` → each ReAct step request reads
  `→ <model> · <n> messages · step(<enabled tools>, answer)`.
- [ ] Disable `web_search` in `/tools`, ask again → `web_search` is gone from the `step(…)` list.
- [ ] After « J'ai du mal avec les suites », `/logs` shows the memory extraction request with
  `schema(facts, forget)`.
- [ ] **Negative**: covered by the automated tests (`tests/core/agent/test_step.py`): a step that is
  not valid JSON becomes an answer instead of looping; an invalid memory extraction writes nothing.

## Known gaps

- `web_search` has no unit test of its own.
- `scripts/benchmark.py` has no tests for its answer checks; read the answers marked wrong before
  trusting a score ([method](../benchmark.md#checking-correctness)).
- The sandbox live tests have not been run on the test machine.
