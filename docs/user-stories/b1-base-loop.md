# [B1] Base CLI chatbot: user stories

Target user: [Titouan](../user-profile.md).

## B1-1 · Watch the answer being written and ask follow-up questions

**As** Titouan, a Terminale maths-speciality student who revises in the evening on a laptop
without a GPU,
**I want** to see Sensai's answer appear as it is written and to ask follow-up questions about the
same exercise,
**so that** I can start reading the method without waiting for the whole generation, and never
paste the exercise again each time I get stuck on a step.

Link to the scenario: [typical session](../user-profile.md#a-typical-session), steps 2 and 3.

Acceptance criteria:

- `uv run sensai --model llama3.2:3b --config config/sensai.toml` opens the chat interface.
- After sending « Résous x² − 5x + 6 = 0 », the answer appears piece by piece during the
  generation, not as one block at the end.
- The next question « Pourquoi tu calcules le discriminant ? » gets an answer about this equation
  without the exercise being repeated.
- `Esc` during a generation stops it and shows `(interrupted)`; a new message can be sent right
  away.

Check: `uv run pytest tests/core/test_engine.py tests/adapters/ollama/test_chat.py tests/adapters/tui/test_chat_app.py`

## B1-2 · Understand what is wrong when Sensai cannot answer

**As** Titouan, who is not a developer and starts Sensai on his own in the evening,
**I want** a clear message when Ollama is down, the model is not installed or I send an empty
message,
**so that** I know what to fix myself instead of thinking Sensai is broken and giving up my
revision session.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), a
lone, non-technical user.

Acceptance criteria:

- With Ollama stopped, sending a message shows an error in the chat containing
  `cannot reach Ollama at http://localhost:11434`; the application stays open.
- After `ollama serve`, the next message gets an answer without restarting Sensai.
- With `--model` set to a model that was not pulled, sending a message shows Ollama's error saying
  the model is not found; the application stays open.
- An empty message (or one made of spaces) is not sent to the model and shows
  `Type a message and press Enter. /exit to quit.`

Check: `uv run pytest tests/adapters/ollama/test_chat.py tests/adapters/tui/test_chat_app.py`, then
the manual test with Ollama stopped described above.

## B1-3 · Pick the model that fits his computer

**As** Titouan, whose laptop has no graphics card,
**I want** to choose the model at start-up without touching the code,
**so that** I use a model light enough to answer within a few seconds on my machine, and move to a
bigger one if I change computers.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
hardware.

Acceptance criteria:

- `--model llama3.2:3b` and `--model qwen3:8b` start the chat with the requested model; `/usage`
  shows the name of the loaded model.
- The configuration file is chosen with `--config`; the Ollama URL is read from it
  (`[ollama] url`).
- Running `uv run sensai` without `--model` or `--config` stops with
  `--model and --config are required to start the chat`.

Check: `uv run pytest tests/test_cli.py tests/test_config.py`

## B1-4 · Read formulas as maths, not as LaTeX code

**As** Titouan, who has never written LaTeX,
**I want** the formulas in Sensai's answers to look like the maths in my textbook,
**so that** I read `x = (−b ± √Δ)/(2a)` instead of `\frac{-b \pm \sqrt{\Delta}}{2a}`, and follow the
calculation instead of decoding it.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
notation used in French *lycée* maths.

Acceptance criteria:

- An answer containing `$\frac{-b \pm \sqrt{\Delta}}{2a}$` is shown as `(-b ± √Δ)/(2a)`.
- Powers and indices become superscripts and subscripts: `x^2 + y^{10} = z_1` is shown as
  `x² + y¹⁰ = z₁`.
- Symbols are shown as such: `\mathbb{R}` as `ℝ`, `\leq` as `≤`, `\sqrt{x^2+1}` as `√(x²+1)`.
- An incomplete formula, for example cut by an interruption, is shown without crashing the chat.

Check: `uv run pytest tests/adapters/tui/test_latex.py tests/adapters/tui/widgets/test_math_markdown.py`
