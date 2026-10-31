# Model benchmark

`scripts/benchmark.py` compares Ollama models on what matters for
[Titouan](user-profile.md): how fast they answer and how much memory they take on the machine he
actually has, and whether their answers to Terminale maths exercises are right.

```bash
uv run python scripts/benchmark.py --config config/benchmark.toml
uv run python scripts/benchmark.py --models llama3.2:3b qwen2.5:7b   # only some models
uv run python scripts/benchmark.py --cases integrale loi-binomiale  # only some questions
```

Each run writes `benchmarks/results/<date>_<time>-<machine>/`:

- `report.md`: the comparison tables;
- `results.json`: every answer, its final line, every measurement and judge reason, and the
  settings and questions used, so the run can be reread or replayed.

Results are committed: they are the evidence for the model choice.

## What is fixed

Every model gets exactly the same inputs, so the only thing that changes is the model:

| Setting | File | Value |
|---|---|---|
| Questions | `benchmarks/cases.toml` | 11 Terminale maths questions + 3 generic ones |
| System prompt | `config/benchmark.toml`, `[prompt]` | A patient maths tutor for Titouan, ending with `Réponse finale : …` |
| Generation | `config/benchmark.toml`, `[generation]` | `temperature = 0`, `seed = 42`, `num_ctx = 4096`, `num_predict = 1024` |

`temperature = 0` and a fixed seed make the answers reproducible: running the benchmark again
with the same model, settings and Ollama version gives the same answers.

The benchmark measures the **model alone**, with Sensai's tutor prompt but without the ReAct loop,
tools or memory: those would add calls whose number depends on the model, and hide the model's own
speed and quality.

## What is measured

| Metric | How |
|---|---|
| Load (s) | `load_duration` reported by Ollama for the first request: cold start of the model |
| First token (s) | Wall-clock time from the request to the first streamed token: what Titouan waits before reading |
| Generation (tok/s) | `eval_count / eval_duration`: the speed at which the answer is written |
| Prompt (tok/s) | `prompt_eval_count / prompt_eval_duration`: the speed at which the question is read |
| Answer time (s) | Wall-clock time of a whole answer |
| Memory (GiB) | `size` from `/api/ps` once the model is loaded with `num_ctx = 4096`: weights, KV cache and buffers |
| Of which VRAM (GiB) | `size_vram` from `/api/ps`; 0 means the model runs entirely on the CPU and system RAM |
| Use case / generic correct | Answers whose final line matches the expected result (see below) |
| Final line given | Answers that follow the `Réponse finale : …` instruction |
| Truncated | Answers cut by `num_predict` (`done_reason = "length"`) |
| Judge (1-5) | Optional: a model grades how well the answer explains the method |

Each model is unloaded (`keep_alive = 0`) before the next one, so its memory is measured alone.

### Checking correctness

Every question in `benchmarks/cases.toml` has `must_match` regexes, and sometimes
`must_not_match` ones. They are applied to the final line of the answer, after normalization
(lowercase, no spaces, decimal commas as dots, `^2` as `²`…). For example, the logarithm
question expects `x = 3` and rejects an answer that keeps the out-of-domain solution `x = −1`.

A question without `must_match` (the proof by induction) has no single result to check: only the
judge grades it.

Always read the answers marked wrong in `results.json`: a check can be too strict (the first run
rejected `S = 253` because it also expected `u₁₀ = 43` on the final line). After fixing
`cases.toml`, check the saved answers again without running any model:

```bash
uv run python scripts/benchmark.py --rescore benchmarks/results/<run>
```

Only the checks change; the answers, timings and memory stay as measured.

### The judge

With `[judge] enabled = true`, a model grades each answer from 1 to 5 on how well it explains the
method to a struggling student, with a JSON schema and `temperature = 0`. It runs after all the
benchmarked models, so it never shares memory with them.

Limits: a 3B-8B judge is weak, and a model judging its own answers is biased. Use the judge score
to rank answers that the regexes cannot check, not as a precise grade.

## Benchmarking another machine

Copy `config/benchmark.toml`, change `[machine]` (it names the results folder and appears in the
report) and the model list, then:

```bash
uv run python scripts/benchmark.py --config config/benchmark-<machine>.toml
```

Keep `[generation]` and `[prompt]` unchanged across machines, or the results are no longer
comparable.

## Adding a model

```bash
ollama pull gemma3:4b
```

then add it to `[run] models`. A model that is not installed is reported as an error in the
report; the other models still run. Cloud models (names ending in `-cloud`) are not local:
benchmarking them would send Titouan's data off his machine, which the
[profile](user-profile.md#constraints-this-puts-on-the-system) rules out.
