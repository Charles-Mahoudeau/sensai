# [A4] Prompt Versioning: user stories

Issue: #40. Design and usage: [docs/core/prompts.md](../core/prompts.md).

## Keep a history of every prompt version

As a developer, I want to keep a history of every prompt version with timestamps, so that I can
see what changed and when.

Acceptance criteria:

- Saving a new prompt creates a new version with a timestamp
  (`sensai prompts new <name> <file>`, or editing a default in `core/prompts/defaults/`).
- Versions can be listed (`sensai prompts list`, `sensai prompts history <name>`).
- Two versions can be diffed (`sensai prompts diff <name> <old> <new>`).

## Roll back and compare versions

As a developer, I want to roll back to a previous prompt version and compare it with the current
one, so that I can undo a regression and measure which version performs better.

Acceptance criteria:

- Rollback makes the old version active (`sensai prompts rollback <name> <version>`), and the chat
  uses it from its next start.
- A comparison run on the same inputs reports latency and quality per version
  (`sensai prompts compare <name> <a> <b> --inputs <file>`).
- Results are logged (`--output report.json` saves every answer, metric and judge verdict).
