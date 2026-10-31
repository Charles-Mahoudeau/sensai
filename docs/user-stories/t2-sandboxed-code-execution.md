# [T2] Sandboxed code execution: user stories

Design: [docs/core/sandbox.md](../core/sandbox.md),
[choice of mechanism](../architecture/sandbox-mechanism.md).
Target user: [Titouan](../user-profile.md).

## T2-1 · Computed results, not guesses

**As** Titouan, who learns his method by following Sensai's calculations,
**I want** Sensai to compute results (solving, simplifying, derivatives, integrals) by running
Python rather than in its head,
**so that** I do not learn a method from a wrong result, which often happens with a small model
that calculates mentally.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he
reads".

Acceptance criteria:

- « Calcule l'intégrale de x·eˣ entre 0 et 1 » shows a `run_python` call in the reasoning block,
  with the script's output.
- The value given in the answer is the one the script printed (here 1).
- `sympy`, `numpy`, `scipy`, `matplotlib` and `pandas` are available without any install.
- The code is only shown in the answer if Titouan asks for it.

Check: `uv run pytest tests/core/tools/builtin/test_python.py tests/adapters/sandbox`

## T2-2 · Check a probability with a simulation

**As** Titouan, who does not see why a binomial distribution gives this result,
**I want** Sensai to simulate the random experiment and compare the frequency it gets with the
theoretical value,
**so that** I see concretely that the formula from the course matches what happens when the
experiment is repeated.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), the
Terminale curriculum (probability).

Acceptance criteria:

- « Simule 10 000 fois 10 lancers d'une pièce et compare la fréquence de 5 piles à P(X = 5) pour
  X ~ B(10 ; 0,5) » triggers a `run_python` call that holds the data and the simulation.
- The frequency and the probability given in the answer come from the script's output.
- The executed script is saved in the run's folder, under `artifacts/`.

Check: the manual test above, then `ls artifacts/`.

## T2-3 · See and keep the plots

**As** Titouan, who understands a function better when he sees its curve,
**I want** the plots drawn by Sensai to appear in the chat and be saved,
**so that** I can link the table of variations or the convexity to the shape of the curve, and
keep the figure for my revision notes.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), the
Terminale curriculum (derivatives and convexity).

Acceptance criteria:

- « Trace f(x) = x·e⁻ˣ sur [0 ; 5] » shows the figure in the interface.
- Every file the script saves is kept under `artifacts/<YYYY-MM-DD>/<HHMMSS>-<id>/`, and its path
  is shown.
- The image stays visible when the reasoning block folds.

Check: `uv run pytest tests/adapters/tui`, then the manual test above.

## T2-4 · Sensai fixes its own code

**As** Titouan, who cannot program in Python,
**I want** Sensai to fix its code on its own when it fails,
**so that** I get the result without having to read or understand a Python error.

Link to the scenario: [who he is](../user-profile.md#who-he-is), a high-school student, not a
developer.

Acceptance criteria:

- A failing script sends back to the model its exit code and the end of the traceback, followed by
  `The code failed: read the error above, fix the code and call run_python again.`
- The model calls `run_python` again with fixed code; the new attempt is visible in the reasoning
  block.
- Attempts are bounded: after two failures in the same turn, `run_python` is no longer offered and
  Sensai answers with what it knows.

Check: `uv run pytest tests/core/agent/test_re_act.py tests/core/tools/builtin/test_python.py`

## T2-5 · Running code with no risk to the computer

**As** Titouan, who uses the family computer,
**I want** the code written by the model to be unable to damage anything on my machine,
**so that** I can let Sensai run code without reviewing it, which I would not know how to do.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), a
personal or family computer.

Acceptance criteria:

- The code has no network access.
- It can neither read nor change my files: only its run folder is writable.
- A run is stopped at the time limit (`[sandbox] timeout`, 30 s by default); a stop for exceeding
  the memory limit (`memory`) is explained to the model.
- No container is left after a run (`docker ps -a`).
- Without Docker or without the image, Sensai still starts without `run_python`, and `sensai.log`
  says why, with the `docker build` command to run.

Check: `uv run pytest tests/adapters/sandbox`
