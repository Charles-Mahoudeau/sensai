# [A1] ReAct reasoning loop: user stories

Target user: [Titouan](../user-profile.md).

## A1-1 · See how Sensai reasons before answering

**As** Titouan, who used to copy the solutions of general-purpose assistants without
understanding the approach,
**I want** to see Sensai's reasoning steps and the tools it uses before its answer,
**so that** I follow the path that leads to the method, and spot myself when a step does not hold
instead of blindly trusting the result.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "understand the
method" and "trust what he reads".

Acceptance criteria:

- With `thinking_effort = "medium"`, every answer is preceded by a reasoning block showing the
  agent's thoughts, then each tool called with its trimmed result.
- The final answer appears after this block, streamed.
- A turn never goes beyond the number of cycles of the effort level (5 for `medium`).
- A tool already called with the same arguments in the turn is not called again: the agent
  answers with what it knows.

Check: `uv run pytest tests/core/agent/test_re_act.py tests/core/agent/test_step.py tests/core/agent/test_thought_stream.py`

## A1-2 · Set the thinking effort for the exercise

**As** Titouan, who switches between quick questions about the course and long exercises on a slow
laptop,
**I want** to choose how much Sensai thinks before answering,
**so that** I get a fast answer when I check a definition, and deeper reasoning when I am stuck on
a hard exercise.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
hardware and latency.

Acceptance criteria:

- The default effort is set without code in `config/sensai.toml` (`[agent] thinking_effort`):
  `none`, `low`, `medium`, `high` or `ultra`.
- `/effort none` answers directly, without a reasoning block; `/effort high` allows up to 12
  cycles; the active level is shown under the prompt.
- `/effort` with an unknown level shows `Unknown effort '…'. Use one of: …` and changes nothing.

Check: `uv run pytest tests/adapters/tui/commands/test_builtin.py tests/test_config.py`

## A1-3 · An answer even when a tool fails

**As** Titouan, who sometimes revises without a reliable internet connection,
**I want** Sensai to answer anyway when a tool fails, and tell me what did not work,
**so that** I am not left in front of a spinning screen, nor given a made-up result in place of
the tool's.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he
reads".

Acceptance criteria:

- A tool that raises an error is shown as failed in the reasoning block, with the error message;
  the turn goes on and ends with an answer.
- A tool that fails twice in the same turn is no longer offered to the model for that turn.
- A call to a disabled tool is refused with `Tool '…' is disabled`, without crashing.

Check: `uv run pytest tests/core/agent/test_re_act.py tests/core/tools/test_registry.py`, then the
manual "Ollama up, network down" test of [T3-2](t3-web-search.md).
