# T2 - Sandboxed Code Execution

## Computed answers

As a mathematician, I want the assistant to solve, simplify or integrate by
running Python, so that I get exact, computed results, not guesses.

Acceptance criteria:

- The agent writes a script and runs it with `run_python` in the sandbox.
- The answer comes from what the script printed.
- `sympy`, `numpy`, `scipy`, `matplotlib` and `pandas` are available without
  any install.

## Data analysis

As a user, I want to ask the assistant to analyze a CSV by running Python, so
that I get computed results, not guesses.

Acceptance criteria:

- The agent writes and runs code in the sandbox, with the data in the script.
- The result comes from the execution output.
- The executed script is saved next to the run's files, under the artifacts
  directory.

## Plots as artifacts

As a mathematician, I want plots drawn by the assistant to appear in the chat
and be saved, so that I can look at them and reuse them.

Acceptance criteria:

- A figure saved by the script is shown inline in the terminal UI.
- Every file the script saves is kept under
  `artifacts/<YYYY-MM-DD>/<HHMMSS>-<id>/`, and its path is shown.
- The image stays visible when the reasoning group folds.

## Self-correction

As a user, I want to let the assistant fix its own code when it fails, so that
I don't have to debug it myself.

Acceptance criteria:

- A traceback is fed back to the agent.
- The agent retries with corrected code.
- It stops after a limited number of attempts.

## Safe execution

As a user, I want model-written code to be unable to harm my machine, so that I
can let the assistant run code without reading it first.

Acceptance criteria:

- The code has no network access.
- It can't read or change my files: only its own run folder is writable.
- A run is stopped at the time limit, and a memory-limit kill is explained.
- No container is left behind after a run.
- Without Docker or the image, Sensai still starts and explains how to enable
  code execution.
