# [M3] External structured memory: user stories

Target user: [Titouan](../user-profile.md).

## M3-1 · Sensai remembers my weak points

**As** Titouan, who often gets stuck on the same topics (sequences, proof by induction),
**I want** Sensai to remember on its own what I tell it about myself and my difficulties,
**so that** its explanations focus on what I have not mastered, from one session to the next,
without me reminding it.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "not repeating
himself", and [typical session](../user-profile.md#a-typical-session), step 5.

Acceptance criteria:

- After « J'ai beaucoup de mal avec les raisonnements par récurrence », a `memory_create` call
  appears in the chat after the answer.
- The fact is saved in the `memories` table of `sensai.db`
  (`sqlite3 sensai.db "SELECT name, type, description FROM memories"`).
- After `/clear` or a restart, « Qu'est-ce que tu sais de moi ? » gets an answer that mentions
  proof by induction.
- A message with no information about the user (« Combien font 12 × 7 ? ») saves nothing.
- The memories are added to the system message of every turn, under
  "What you remember about the user" (`tests/core/agent/test_memory_recall.py`).

Check: `uv run pytest tests/core/agent/test_memory_extraction.py tests/core/agent/test_memory_recall.py tests/adapters/storage/repositories/test_memory_repository.py`

## M3-2 · Correct what Sensai knows about me, or make it forget

**As** Titouan, who makes progress and whose situation changes over the year,
**I want** to tell Sensai that something is wrong or out of date, or ask it to forget it,
**so that** its explanations follow my real level and it does not keep information about me, a
minor, that I no longer want stored.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
privacy of a minor.

Acceptance criteria:

- After « Maintenant je maîtrise la récurrence, c'est plutôt les intégrales qui me posent
  problème », a `memory_update` call (or `memory_delete` then `memory_create`) appears, and the
  `memories` table no longer lists induction as a difficulty.
- After « Oublie ce que tu sais sur mes difficultés », a `memory_delete` call appears and the
  matching row disappears from `memories`.
- An extraction whose JSON is invalid is skipped and written to `sensai.log`; the conversation
  goes on normally.

Check: `uv run pytest tests/core/agent/test_memory_tools.py tests/core/tools/builtin/test_memory.py`

## M3-3 · Turn the memory off

**As** Titouan, who sometimes lends his computer to a classmate to revise,
**I want** to turn the long-term memory off,
**so that** what my classmate says is neither saved in my profile nor mixed with my own memories.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
privacy.

Acceptance criteria:

- In `/tools`, disabling `memory_create`, `memory_update` and `memory_delete` stops every write:
  after « J'ai du mal avec les probabilités », no memory call appears and the `memories` table
  does not change.
- Disabling `memory_read` removes the memories from the system message.
- Started with `--no-tools`, Sensai neither shows nor saves any memory.

Check: `uv run pytest tests/core/agent/test_re_act.py tests/core/agent/test_memory_recall.py`
