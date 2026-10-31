# [M1] Session persistence and profile: user stories

Target user: [Titouan](../user-profile.md).

## M1-1 · Resume yesterday's exercise

**As** Titouan, who works on the same chapter over several evenings,
**I want** to find my previous conversations and resume one,
**so that** I continue yesterday's exercise where I stopped, without explaining everything to
Sensai again.

Link to the scenario: [typical session](../user-profile.md#a-typical-session), step 5 (the next
day).

Acceptance criteria:

- After an exchange, quitting Sensai (`/exit`) and starting it again shows the last conversation.
- After its first exchange, each session gets a short title generated from its content.
- `/sessions` (or `/chats`) opens the list of saved sessions, most recent first, with their
  titles; choosing one shows its messages again, and the next message continues that
  conversation.
- `/clear` clears the screen and starts a new session; the previous one stays in `/sessions`.
- Choosing a session while an answer is running is refused with
  `(cannot switch sessions while an answer is running)`.

Check: `uv run pytest tests/core/test_sessions.py tests/adapters/storage/repositories/test_session_repository.py`

## M1-2 · Never repeat his level in each conversation

**As** Titouan, a struggling Terminale maths-speciality student,
**I want** to describe once and for all my level, my language and how I want things explained,
**so that** every answer fits my level from the first question, unlike general-purpose assistants
that start from zero in every conversation.

Link to the scenario: [his problem](../user-profile.md#his-problem), "they forget him", and
[typical session](../user-profile.md#a-typical-session), step 1.

Acceptance criteria:

- `config/profile.toml` accepts the `[identity]`, `[preference]`, `[instruction]` and `[other]`
  sections, with free keys and non-empty string values.
- With `instruction.style = "Réponds en français et détaille chaque calcul"`, a question asked in
  English gets an answer in French with the intermediate calculations.
- The profile is sent in the system message, after the persona, on every turn: it is visible in
  the `Chat payload` written to `sensai.log`.
- An unknown section (for example `[hobbies]`) stops the start-up with `unknown section [hobbies]`
  and the list of allowed sections.
- Without a profile file, Sensai starts with an empty profile.
- A change to the file applies at the next start.

Check: `uv run pytest tests/adapters/profile tests/core/test_engine.py`
