# Feature choices

Sensai has one user: [Titouan](../user-profile.md), 17, struggling in Terminale maths, revising alone
in the evening on a laptop with no dedicated GPU. Every feature is kept or left out for what it
does for him, under the project's constraints: a local Ollama model, no LLM framework, and his
hardware, where the [benchmark](../benchmark.md) measured 5 to 12 tokens/s and 35 to 70 s per answer.

That speed is the main constraint on the scope: every extra model call per turn costs Titouan tens
of seconds. A few features that work together are worth more than a long list, and the grading
caps the feature total for the same reason.

## Implemented

| Feature | What it does for Titouan | User stories |
|---|---|---|
| [B1] Base CLI chatbot | Streams the answer so he reads while it is written; clear errors he can fix alone; a model chosen for his laptop | [B1](../user-stories/b1-base-loop.md) |
| [M1] Sessions and profile | He resumes yesterday's exercise and never explains his level again | [M1](../user-stories/m1-session-persistence-profile.md) |
| [M3] Structured memory (SQLite) | Sensai remembers his weak points across sessions, and forgets them when he asks | [M3](../user-stories/m3-structured-memory.md) |
| [A1] ReAct loop | He sees the reasoning that leads to the method, not just a result to copy | [A1](../user-stories/a1-react.md) |
| [A5] Personas | Another way of explaining when the first one does not click, without losing the exercise | [A5](../user-stories/a5-persona.md) |
| [T2] Python sandbox | Results are computed, not guessed: a small model makes calculation errors (see the benchmark) | [T2](../user-stories/t2-sandboxed-code-execution.md) |
| [T3] Web search | Up-to-date facts about the bac (dates, curriculum, past papers) that a local model cannot know | [T3](../user-stories/t3-web-search.md) |
| [T1] MCP | External tool sources plugged in from the configuration | [T1](../user-stories/t1-mcp.md) |
| [T5] Structured output | A small model picks tools and writes memories in a format the code can check | [T5](../user-stories/t5-structured-output.md) |
| [A4] Prompt versioning | The team measures that a prompt change explains better before Titouan gets it | [A4](../user-stories/a4-prompt-versioning.md) |

### Changed along the way

| Feature | Change | Stories affected |
|---|---|---|
| [T5] Structured output | The `plan` mode was built but nothing in the chat turns it on. T5 now rests on the ReAct steps, the memory extraction and the prompt judge. | Former T5 stories on plans, replaced by [T5-1 to T5-3](../user-stories/t5-structured-output.md) |
| [T1] MCP | The only server of our own is `scripts/fake_mcp_server.py` (`echo`); a server useful to Titouan is still to be built, and the client only speaks HTTP | [T1-2](../user-stories/t1-mcp.md) |
| [X2] Branching | Only the interrupt part exists (`Esc`); there is no editing of a past message and no branch. Not presented as a feature. | Covered by [B1-1](../user-stories/b1-base-loop.md) only |

## Planned, not done yet

These are on the team's backlog with a high priority. They are not counted as implemented until
every acceptance criterion passes.

| Feature | Why it matters for Titouan | Risk to handle |
|---|---|---|
| [M2] Token budgeting and compression | A long revision evening fills the context window; today Ollama silently drops the oldest turns, so the exercise statement can disappear | A summary that loses a number from the statement teaches him a wrong method |
| [A3] Human-in-the-loop | `memory_delete` is irreversible, and `run_python` already declares `requires_confirmation`, which nothing enforces yet | Too many confirmations break the flow of a 17-year-old revising alone: confirm only irreversible actions |
| [T4] File access with permissions | He could hand Sensai the exercise sheet or his notes as a file instead of retyping them | The agent must only read the folders he allows, on a family computer |
| [A6] Semantic cache | Instant answers to questions he asks again (definitions, course points) | Two exercises can be close in meaning but have different answers (x² − 5x + 6 = 0 and x² − 5x − 6 = 0): a cache hit would serve a wrong answer. Limit it to course questions, with a strict threshold |
| [A7] Prompt optimization | Few-shot examples chosen by the topic of the exercise | Each extra example lengthens the prompt, which costs reading time on his CPU |
| [EV2] Guardrails | He is a minor: keep the tutor on maths, and keep personal data out of the logs | False refusals on legitimate maths questions |
| [EV3] Logging and metrics | Shows the team where his evenings are slow or fail | The logs hold a minor's questions: keep them local and anonymized |

## Left out on purpose

| Feature | Why not, for Titouan |
|---|---|
| [R1] / [R2] RAG | The Terminale curriculum is standard knowledge the models already have; the benchmark errors are calculation and reasoning errors, which the sandbox ([T2]) addresses, not missing knowledge. RAG would add an embedding model and a vector store to run on his CPU for little gain. |
| [A2] Multi-agent | Several agents mean several model calls per answer: on his laptop, a 70 s answer would become several minutes. One agent with tools does the job. |
| [X1] Web UI | He uses Sensai alone on his own computer; the terminal UI already streams answers, shows reasoning and has panels. A web UI would add a server and a second front-end to secure without a new use. |
| [X3] Export and publication | A public link would send a minor's questions and profile off his machine, which goes against the local-only choice. |
| [X5] Scheduling | He opens Sensai when he revises; nothing needs to run while he is away, and a background model would slow down his computer. |
| [M4] Artifact document | A revision sheet built across turns would be useful, but each update is an extra model call per turn, and he does not need it to understand an exercise. |
| [EV1] Hallucination detection | An LLM judge on every answer doubles the time per turn. Computed results ([T2]) and visible reasoning ([A1]) address wrong answers more cheaply. |
| [EV4] Adversarial testing | Sensai has one trusted local user and no exposed service; the attack surface that matters (model-written code) is contained by the sandbox instead. |
| [X4] Questions and forms | The model asking him multiple-choice questions does not fit a free-form maths conversation better than plain text. |
