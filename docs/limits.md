# Limits

Where Sensai breaks, with what we saw during testing. Unless stated otherwise, everything below
was observed on the test machine (Intel Core i5-1335U, 16 GB RAM, no dedicated GPU, CPU inference)
with `qwen2.5:7b`, the model the [benchmark](benchmark.md) selected.

Sources:

- the benchmark run [2026-10-31](../benchmarks/results/2026-10-31_2337-matthieu-laptop/report.md)
  (3 models, 14 questions, every answer in `results.json`);
- the [demo videos](features/demos/), recorded with the real application and the real model;
- the session logs of those demos (`/logs`, `sensai.log`).

## Summary

| Limit | Impact for Titouan | Seen in |
|---|---|---|
| [One message takes 1 to 7 minutes](#latency) | He waits a long time; a revision evening holds few exchanges | All demos |
| [Small models make maths errors](#wrong-answers) | He can learn a wrong method | Benchmark |
| [The calculator is not always called](#tools-are-not-always-used) | A number in an answer may come from the model's head | `ev3-logs`, `a1-calculator` |
| [Web answers cite no source, and the model does not know today's date](#web-search) | He cannot check what Sensai found | `t3-web-search` |
| [The context is not capped](#context-and-memory) | In a long session, the oldest messages can be dropped without warning | Code review, not observed |
| [Formulas lose spaces or stay as raw LaTeX](#display) | Some formulas are hard to read | `b1-chat`, `m1-sessions`, `m3-memory`, `a5-persona` |
| [The tone does not fit him yet](#tone-and-level) | Formal, sometimes above his level | `b1-chat`, `m1-sessions` |
| [What Sensai knows about him is stored unencrypted](#data-and-privacy) | Personal data of a minor on a shared computer | `sensai.db` |
| [Parts not verified](#not-verified) | Unknown behaviour of the sandbox and of third-party MCP servers | — |

## Latency

**What we saw.** One message takes from about 1 minute to 7 minutes:

| Message | Total | Detail |
|---|---|---|
| « Bonjour » (`llama3.2:3b`) | 75 s | Reasoning step 37 s (model load included), answer 23 s, memory extraction 12 s, session title |
| « Combien font 2 ^ 10 ? » | 65 s | Reasoning step 52 s, answer 9 s, title 4 s (`ev3-logs`) |
| « Combien font (12,5 × 4)² / √16 ? » | 155 s | 2 reasoning steps and 1 calculator call: 135 s before the answer (`a1-calculator`) |
| « Quelles étaient les dates des épreuves de spécialité du bac 2026 ? » | 192 s | 2 steps and 1 web search: 167 s before the answer (`t3-web-search`) |
| « J'ai beaucoup de mal avec les raisonnements par récurrence. » | 412 s | The model searched the web, unasked, then wrote a long answer (`m3-memory`) |

**Why.** On this CPU, `qwen2.5:7b` writes 5.6 tokens/s and reads 73 tokens/s (benchmark). A
message triggers several model calls in a row: at least one ReAct step, the answer, the memory
extraction, and the session title on the first message. Each call first reads the whole prompt,
about 1,100 to 1,350 tokens (system prompt, persona, profile, tool descriptions, history), which
alone costs about 15 s.

**Impact.** The answer streams, so Titouan reads while it is written, but he waits 50 s or more
before the first word of the answer: the reasoning steps come first. A revision evening of an hour
holds about 20 to 30 exchanges.

**What would help.** `/effort none` skips the reasoning steps (the `17 × 23` answer in
`a1-calculator` came in about 15 s), at the cost of tool use. A shorter system prompt, fewer tool
descriptions, or skipping the memory extraction on messages that state nothing about the user
would cut the reading time of every call. A GPU would change the order of magnitude.

## Wrong answers

**What we saw.** On the 10 checkable maths questions of the benchmark:

| Model | Correct | Mistakes |
|---|---|---|
| `llama3.2:3b` | 6/10 | Derivative of x³ − 3x² + 2x − 1 given as `x - 3x² + 2x³`; ln(x) + ln(x − 2) = ln(3) solved as if the right side were 3, giving `1 + √(1 + e³)`; P(B) = 0.8 instead of 0.32; sum of the sequence 210 instead of 253 |
| `llama3.1:8b` | 7/10 | Limit of (2x² + 1)/(x² − 3) given as 0 instead of 2; P(B) = 0.38; sum 231 |
| `qwen2.5:7b` | 10/10 | — |

`llama3.2:3b` also looped on the proof by induction, writing the same line again until it was cut
at 1,024 tokens. No model counted the 3 « r » of « arrière » (all answered 2).

**Why.** Small models compute in their head token by token and get multi-step calculations wrong.
Counting letters fails because the model sees chunks of words (tokens), not letters.

**Impact.** A struggling student cannot spot a wrong derivative: he learns it. This is why Sensai
uses `qwen2.5:7b` and calls tools for calculations. But 10/10 is on 10 questions only: it shows
`qwen2.5:7b` is clearly better than the two others, not that it never makes mistakes.

## Tools are not always used

**What we saw.**

- « Combien font 2 ^ 10 ? »: the model thought « c'est une opération de base de calcul » and
  answered `2¹⁰ = 1024` without calling the calculator, although the system prompt asks for it on
  every calculation (`ev3-logs`).
- With `/effort none`, no tool can be called at all: « Combien font 17 × 23 ? » was answered from
  the model's head (`391`, correct this time) (`a1-calculator`).
- The model ran a web search that nobody asked for when Titouan only said he struggles with
  induction (`m3-memory`).

**Why.** Whether to call a tool is the model's decision. The step schema only restricts *which*
tools it can call, not *when* it must.

**Impact.** Story [T1-5](user-stories/t1-mcp.md) promises a calculator call for every calculation:
that is not guaranteed. A wrong mental calculation would reach Titouan without any warning.

## Web search

**What we saw** (`t3-web-search`):

- The answer gave the dates (« du 16 au 18 juin ») but **no URL**, although the search results
  had them. Story [T3-1](user-stories/t3-web-search.md) expects at least one.
- It wrote « auront lieu » for an exam that had already taken place: the model does not know
  today's date.
- The second reasoning step repeated the first thought word for word.

**Impact.** Titouan cannot check where an answer comes from, and dates can be read in the wrong
tense.

**Not observed, but possible.** The search goes through DuckDuckGo without an API key: it can be
rate-limited or change its results page, and then the tool fails.

## Context and memory

**Context window.** Sensai sends no `num_ctx` to Ollama, so the model runs with Ollama's default
window, and there is no token budget or summary of old messages (M2 is not implemented). When a
conversation outgrows the window, Ollama drops the oldest tokens without telling Sensai: in a long
session, the exercise statement could disappear from what the model sees. `/usage` shows how full
the context is, but nothing reacts to it. We did not run a session long enough to observe it.

**Exact prompt.** The full request sent to Ollama is only logged at DEBUG level, and Sensai logs
from INFO up: the exact prompt of a turn cannot be shown today. `/logs` only shows a one-line
summary per request.

**Sessions.** Restarting Sensai opens a new, empty session; the previous one has to be resumed
with `/sessions` (`m1-sessions`). The README and story [M1-1](user-stories/m1-session-persistence-profile.md)
still say it is restored at start-up.

## Display

**What we saw.**

- The space after an inline formula disappears: « x² − 5x + 6 = 0est donnée », « x = 2et »,
  « uₙoù », « N ∈ ℕtel » (`b1-chat`, `m1-sessions`).
- Display formulas written as `\[ … \]` stay as raw code: « [ \sum_{k=0}^{p-1} (2k+1) = p^2 ] »,
  « [ \begin{align*} 2x + 3 &= 11 \ … \end{align*} ] » (`m3-memory`, `a5-persona`).

**Impact.** Story [B1-4](user-stories/b1-base-loop.md) promises formulas that read like a
textbook; long derivations are the hardest part to read. The cause is not diagnosed yet.

## Tone and level

**What we saw.** With the default persona, Sensai uses « vous », writes « plus straightforward »
(`b1-chat`), greets « Bonjour User », and answers « Rappelle-moi ce que je révise » with the Cauchy
criterion and series, beyond the Terminale curriculum (`m1-sessions`). With `/persona
vulgarisateur`, the tone fits (« tu », an example with sweets) (`a5-persona`).

**Why.** The default persona (`config/personas/sensai.toml`) is written for « mathematicians »,
and `config/profile.toml` is not Titouan's (`name = "User"`, `language = "Python"`).

## Data and privacy

- The memories are stored as plain text in `sensai.db` (table `memories`), for example that the
  user struggles with induction. Anyone using the same computer account can read them.
- `sensai.log` keeps a 200-character preview of each model reply, and the replies can repeat what
  the user said about himself.
- Everything stays on the machine: no data is sent to a cloud model. Only the web search query
  leaves it, to DuckDuckGo, and a query can contain what the user typed.

## Not verified

- **Python sandbox (T2).** The `sensai-sandbox` Docker image is not built on the test machine: the
  live tests (no network, read-only files, time and memory limits) and the self-correction loop
  were not run there. Without the image, Sensai starts without `run_python`, as expected.
- **Third-party MCP servers (T1).** Only our test server and the GitHub server are configured, and
  GitHub was not tested (no token). The client only speaks the HTTP transport and protocol version
  `2026-07-28`: a server using stdio or an older version will not connect.
- **Ollama down, model not installed (B1).** Covered by the automated and live tests, not shown in
  a demo.
