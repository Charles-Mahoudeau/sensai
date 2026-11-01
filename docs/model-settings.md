# Model Settings

The generation settings change how the model picks its words: how random it
is, which candidates it considers, and how much of the conversation it can see.
Sensai sends them with every thought and answer of the ReAct agent. Memory
extraction, session titles and the prompt judge keep their own fixed settings.

This page explains each setting, how to change it without touching the code,
and what changing it measurably does to math answers.

## The settings

At each step the model scores every possible next token. The settings decide
how one is picked from those scores.

| Setting | What it does | Ollama's default |
| --- | --- | --- |
| `temperature` | How random the pick is. `0` always takes the likeliest token, so the same prompt gives the same answer; higher values give unlikely tokens more chances. | 0.8 |
| `top_p` | Keep only the likeliest tokens whose probabilities add up to `p`, then pick among them. `0.9` drops the long tail of unlikely tokens. | 0.9 |
| `top_k` | Keep only the `k` likeliest tokens, then pick among them. | 40 |
| `seed` | Starts the random generator at a fixed point: the same seed with the same settings, prompt, model and Ollama version gives the same answer. | random |
| `num_ctx` | The context length, in tokens: how much of the conversation the model sees. When a prompt is longer, Ollama **silently drops the oldest tokens**. | 4096 |

`top_k` and `top_p` narrow the candidates first; `temperature` then decides
how boldly to pick among those left. With `temperature = 0` the pick is always
the likeliest token, so `top_p` and `top_k` no longer matter.

## Sensai's values

```toml
[generation]
temperature = 0.1   # math: consistent, reproducible answers
num_ctx = 8192      # tool outputs and tracebacks fill the default 4096 fast
```

- **A low temperature (0.1)**: a math question has one right answer, and asking
  it twice should give it twice. The measurements below show that a low
  temperature makes the answers consistent; a high one gives a different answer
  almost every time.
- **A larger context (8192)**: `run_python` results, tracebacks and earlier
  facts add up quickly. The measurements below show that a fact stated early in
  the conversation is lost with a small context and kept with this one.
- `top_p`, `top_k` and `seed` are left to the model's defaults. Set `seed` to
  make answers fully reproducible, for example to compare prompts.

## Changing them

Neither way needs a code change.

- **For every session:** edit `[generation]` in `config/sensai.toml`. A key left
  out keeps the model's default. Wrong names, types and ranges stop the start
  with a clear error (`temperature >= 0`, `0 <= top_p <= 1`, `top_k >= 1`,
  `num_ctx >= 1`).
- **For the current session:** `/model-settings` in the chat.

  ```text
  /model-settings                    # show the current values
  /model-settings temperature 0.8    # set one, from the next message
  /model-settings num_ctx default    # back to the model's default
  ```

## What changing them does

These results come from `scripts/sampling_experiment.py`. It asks Sensai's
ReAct agent questions with a known answer and checks each answer
automatically. Tools and thinking are turned off, so the tables measure the
model's own answers.

Setup: `qwen2.5:7b`, Ollama 0.34.2, CPU only, the shipped `system` prompt,
`num_ctx = 8192` unless stated otherwise.

### Temperature: consistency

Six questions, each asked with 5 seeds at 3 temperatures (90 answers):

- a 9-digit product (`123456789 × 987654321`)
- an average speed (180 km in 2 h 30)
- a derivative's value (`f'(2)` for `x³ − 5x² + 2x`)
- the roots of `x³ − 6x² + 11x − 6`
- the limit of `(1 + 1/n)^(2n)`
- the probability that two dice sum to 7

```bash
uv run python scripts/sampling_experiment.py --model qwen2.5:7b \
  --temperature 0 0.8 1.5 --seed 1 2 3 4 5
```

| temperature | right | distinct answers per question | time per answer |
|---|---|---|---|
| 0 | 25/30 (83%) | 1.2 | 37 s |
| 0.8 | 25/30 (83%) | 5.0 | 39 s |
| 1.5 | 24/30 (80%) | 5.0 | 36 s |

| question | 0 | 0.8 | 1.5 |
|---|---|---|---|
| product | 0/5 | 0/5 | 0/5 |
| speed | 5/5 | 5/5 | 4/5 |
| derivative | 5/5 | 5/5 | 5/5 |
| roots | 5/5 | 5/5 | 5/5 |
| limit | 5/5 | 5/5 | 5/5 |
| dice | 5/5 | 5/5 | 5/5 |

What it shows:

- **Consistency changes a lot.** At temperature 0, the five seeds give
  practically the same answer (1.2 distinct answers per question). At 0.8,
  Ollama's default, and at 1.5, each of the five seeds gives a different
  answer: different wording, steps, and sometimes a different result. A user
  asking the same question twice should not get two answers. That's why Sensai
  ships `temperature = 0.1`.
- **Accuracy barely changes on these questions:** 83%, 83%, then 80%. The one
  extra error is an average speed at 1.5. These questions are simple enough
  for the model to get right even with random picks. Harder, multi-step
  problems may show a larger drop, since a single badly picked token can derail
  a long derivation. That's not measured here.
- **The product is wrong at every temperature.** No setting makes a 7B model
  multiply two 9-digit numbers in its head. That's what the `run_python` tool
  is for (see [Code Sandbox](core/sandbox.md)): the right setting can't
  replace the right tool.

### Context length: early facts

A fact is stated in the first message ("my constant is k = 7.31"), followed by
about 3,000 tokens of unrelated turns, then a question that needs it. Asked
with 3 seeds at each context length, `temperature = 0.1`:

```bash
uv run python scripts/sampling_experiment.py --model qwen2.5:7b \
  --recall --num-ctx 2048 8192 --seed 1 2 3
```

| num_ctx | recalled k = 7.31 | time per answer |
|---|---|---|
| 2048 | 0/3 (0%) | 49 s |
| 8192 | 3/3 (100%) | 63 s |

- **With 2048 tokens the fact is gone.** The conversation is longer than the
  context, so Ollama drops its start, the fact included, without any warning.
  The model then answers without knowing `k`.
- **With 8192 tokens it is always recalled.** The cost is time: about 30% more
  per answer here, because there are more tokens to read. Memory use grows too.
- That's why Sensai ships `num_ctx = 8192`, above Ollama's 4096. The `/usage`
  panel shows how full the context is.

## Reproducing the tables

The same model, settings, seeds and Ollama version give the same tables. Other
models or versions give other numbers, but the same trends are expected. The
script also takes `--num-ctx` for the temperature run and `--out results.md` to
save its tables.

## Limits

- Five seeds per setting is a small sample: the trends are clear, the exact
  percentages are not precise.
- The questions are checked automatically by pattern (for example `72`,
  `1/6`, `e^2`). An answer that is right but written unusually can count as
  wrong.
- Tools and thinking are off in the experiment. In the chat, `run_python` does
  the exact computations, and the settings mostly affect the reasoning and the
  wording around them.
