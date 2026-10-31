# [A4] Prompt versioning: user stories

Issue: #40. Design and usage: [docs/core/prompts.md](../core/prompts.md).
End user: [Titouan](../user-profile.md). The prompts are tuned for him by the Sensai team.

## A4-1 · Keep the history of the tutor's prompts

**As** a Sensai team member who tunes how the tutor explains maths to Titouan,
**I want** every version of a prompt to be saved with its date and a note,
**so that** I can find which change altered the tutor's behaviour, for example the day it started
skipping calculation steps.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "understand the
method": the `system` prompt is what asks for detailed steps.

Acceptance criteria:

- `uv run sensai prompts list` shows every prompt (`system`, `react_thought`,
  `memory_extraction`…) with its active version.
- `uv run sensai prompts new system my_prompt.md --note "detail every calculation"` creates a new
  active version; `prompts history system` lists it with its number, date and note, the active
  version marked `●`.
- `uv run sensai prompts diff system 1 2` shows the lines changed between the two versions.
- `prompts new` refuses a version that breaks a prompt template (for example `react_thought`
  without its `{tools}` placeholder) with a message saying what is missing, and creates no version.

Check: `uv run pytest tests/core/prompts tests/adapters/cli tests/adapters/storage/repositories/test_prompt_repository.py`

## A4-2 · Measure whether a new version explains better, and roll back otherwise

**As** a Sensai team member who changes the tutor's prompt,
**I want** to compare two versions on the same exercises and go back to the old one if the new
one is worse,
**so that** Titouan only gets a version measured to explain better, without risking a worse tutor
on a hunch.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), the
Terminale curriculum as test data.

Acceptance criteria:

- `uv run sensai prompts compare system 1 2 --inputs <file> --model llama3.2:3b --config config/sensai.toml`
  sends each line of the file to both versions and shows, per version, the mean latency, the
  tokens, the answer length and the number of wins given by the judge.
- The judge is asked twice with the answers swapped, to limit position bias; `--no-judge` only
  computes the metrics.
- `--output report.json` saves every answer, every metric and every reasoned verdict of the judge,
  to replay or reread the comparison.
- `uv run sensai prompts rollback system 1` makes version 1 active; the chat uses it from its next
  start, and `prompts rollback system 2` brings version 2 back (nothing is deleted).

Check: `uv run pytest tests/core/prompts/test_comparison.py tests/adapters/cli`, then a real
comparison saved with `--output`.
