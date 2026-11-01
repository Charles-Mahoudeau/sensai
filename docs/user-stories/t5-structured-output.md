# [T5] Structured output: user stories

Design: [docs/structured-output.md](../structured-output.md).
Target user: [Titouan](../user-profile.md).

## T5-1 · A small model that picks its tools without getting the format wrong

**As** Titouan, who runs a small model on a laptop without a GPU,
**I want** every reasoning step of Sensai to be constrained by a JSON schema that only allows the
available tools,
**so that** I never see a tool call written as raw text, or a made-up tool, in place of the
explanation I expect.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
hardware (a small local model).

Acceptance criteria:

- Every ReAct step request sends a JSON schema in Ollama's `format` field; its `action` field only
  accepts the enabled tools and the final answer. In `/logs`, each step request reads
  `→ <model> · <n> messages · step(<enabled tools>, answer)`.
- A tool disabled in `/tools` disappears from that list from the next message.
- Arguments that do not match the tool's parameters are refused before running, and the error is
  sent back to the model.
- A step that is not valid JSON (for example cut by the length limit) becomes an answer: the turn
  ends instead of looping.
- Answers to Titouan stay free-form text, streamed.

Check: `uv run pytest tests/core/agent/test_step.py tests/core/agent/test_structured.py tests/core/agent/structured`

## T5-2 · Memories saved in a reliable format

**As** Titouan, whose weak points Sensai remembers from one session to the next,
**I want** the facts extracted from my messages to be produced in a strict format and checked
before being saved,
**so that** my memory does not fill up with broken or misfiled rows that would skew later
explanations.

Link to the scenario: [typical session](../user-profile.md#a-typical-session), step 5, and
[M3](m3-structured-memory.md).

Acceptance criteria:

- The memory extraction request sends a `{facts, forget}` schema in `format` (shown as
  `schema(facts, forget)` in `/logs`); each fact has a `subject`, a `fact` and a `category` among
  `preference`, `identity`, `project`, `habit`, `goal`, `other`.
- The answer is parsed and validated against this schema before anything is written to the
  database.
- Invalid or non-conforming JSON writes nothing: the error is written to `sensai.log` and the
  conversation goes on.

Check: `uv run pytest tests/core/agent/test_memory_extraction.py tests/core/agent/test_structured.py`

## T5-3 · A judge verdict that can be counted, to compare two prompts

**As** a Sensai team member who compares two versions of the tutor's prompt,
**I want** the judge to give its verdict in a fixed format,
**so that** the wins of each version are counted automatically instead of rereading free-text
opinions.

Link to the scenario: [A4-2](a4-prompt-versioning.md), measuring that a version explains better to
Titouan.

Acceptance criteria:

- `sensai prompts compare` asks the judge with a JSON schema and a temperature of 0.
- Each verdict gives `winner` (`A`, `B` or `tie`) and `reason`, and appears in the `--output`
  report.
- The total of wins per version is shown at the end of the comparison.

Check: `uv run pytest tests/core/prompts/test_comparison.py`

## T5-4 · A plan of the method, without the answer

**As** Titouan, who copies the solution as soon as he sees it and is stuck again on the next
exercise,
**I want** Sensai to give me only the steps to follow to solve an exercise, without doing the
calculations or giving the result,
**so that** I do the work myself, with a guide, and actually learn the method.

Link to the scenario: [his problem](../user-profile.md#his-problem), "they give the answer, not
the method", and [typical session](../user-profile.md#a-typical-session), step 4 (trying on his
own).

Acceptance criteria:

- In plan mode, « Résous x² − 5x + 6 = 0 » gets a numbered plan: a title, then each step with what
  to do, how to do it and the course notion it uses, then how to check the result.
- The plan gives neither the solutions (2 and 3) nor the intermediate values (Δ = 1): only what to
  compute and how.
- The plan is requested with the `plan` JSON schema in Ollama's `format` field (shown as
  `schema(title, steps, check)` in `/logs`), validated, then shown as readable text: the JSON is
  never displayed.
- In plan mode, no reasoning step and no tool runs: the plan comes from a single model call.
- The plan stays in the conversation: back in the default mode, « J'ai trouvé Δ = 1, c'est
  bon ? » gets an answer about this exercise.
- A reply that does not follow the schema is reported as an error in the chat; Sensai keeps
  running.

Check: `uv run pytest tests/core/agent/test_structured.py tests/core/agent/structured`

## T5-5 · Switch between the default mode and the plan mode

**As** Titouan, who sometimes wants a full explanation and sometimes only a guide to try alone,
**I want** to switch between the default mode and the plan mode during the conversation,
**so that** I choose, exercise by exercise, how much help I get, without losing the exercise in
progress.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "understand the
method".

Acceptance criteria:

- `/mode` shows `Mode: default (available: default, plan)`.
- `/mode plan` switches to plan mode from the next message, shows `Mode: plan`, and the status bar
  shows `Plan mode`; `/mode default` goes back and the label disappears.
- The conversation is kept when the mode changes.
- **Negative**: `/mode bogus` shows `Unknown mode 'bogus'. Use one of: default, plan` and the mode
  does not change.
- **Negative**: changing mode while an answer is running is refused, and the mode does not change.
- **Negative**: with `[structured_output] enabled = false`, `/mode plan` is refused with a message
  naming that setting, and Sensai stays in the default mode.
- Sensai always starts in the default mode.

Check: `uv run pytest tests/adapters/tui/commands/test_builtin.py tests/core/test_engine.py`
