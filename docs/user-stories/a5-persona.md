# [A5] Personas: user stories

Target user: [Titouan](../user-profile.md).

## A5-1 · Change the way of explaining in the middle of an exercise

**As** Titouan, who does not always understand the first explanation,
**I want** to change the tutor's style in the middle of an exercise (simpler, more rigorous…),
**so that** I get another explanation of the same step without pasting the exercise again or
losing what was already done.

Link to the scenario: [typical session](../user-profile.md#a-typical-session), step 3.

Acceptance criteria:

- `/persona` without an argument shows `Persona: <active> (available: …)` with the list of
  personas in `config/personas/`.
- After an exercise solved with the default persona, `/persona vulgarisateur` then
  « Réexplique l'étape 2 plus simplement » gets an answer in the new style that is about step 2
  of that exercise: the history is kept.
- The new persona applies from the next message, without restarting.
- `/persona unknown` shows an error and keeps the active persona.
- Switching persona while an answer is running is refused.

Check: `uv run pytest tests/core/test_persona.py tests/core/test_engine.py tests/adapters/tui/commands/test_builtin.py`

## A5-2 · Create a new tutor style without touching the code

**As** a Sensai team member who prepares tutors for the different moments of Titouan's revision
(lessons, exercises, bac preparation),
**I want** to create or edit a persona with a plain configuration file,
**so that** I can fit the tutor's tone and method to Titouan's needs without changing the code or
redeploying Sensai.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), tone
and language.

Acceptance criteria:

- A `config/personas/examinateur.toml` file with free sections (`[identity]`, `[method]`,
  `[tone]`…) appears in `/persona` right away, without restarting.
- Its sections become titles in the system message, in the order of the file (visible in the
  `Chat payload` of `sensai.log`).
- A value outside a section, or an empty one, makes the selection fail with an error naming the
  file and the faulty key; the active persona does not change.
- `[personas] default = "examinateur"` in `config/sensai.toml` makes it active at start-up;
  removing `default` goes back to the base prompt.

Check: `uv run pytest tests/adapters/persona tests/core/test_persona.py tests/test_config.py`
