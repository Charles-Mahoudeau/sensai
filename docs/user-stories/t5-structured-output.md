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

- Every ReAct step request sends a JSON schema in Ollama's `format` field (visible in the
  `Chat payload` of `sensai.log`); its `action` field only accepts the enabled tools and the final
  answer.
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

- The memory extraction request sends a `{facts, forget}` schema in `format`; each fact has a
  `subject`, a `fact` and a `category` among `preference`, `identity`, `project`, `habit`, `goal`,
  `other` (visible in `sensai.log`).
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
