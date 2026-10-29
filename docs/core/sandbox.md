# Code Sandbox

The `run_python` tool lets the model compute instead of guessing: it writes a
Python script, Sensai runs it in an isolated Docker container, and the model
reads what it printed. Files the script saves, such as plots, are kept for the
user and shown in the terminal UI.

```text
ReActAgent -> ToolRegistry -> run_python -> CodeRunner port -> DockerCodeRunner
```

Why Docker rather than a subprocess is recorded in
[the sandbox ADR](../architecture/sandbox-mechanism.md).

## Setup

Build the image once:

```bash
docker build -t sensai-sandbox src/sensai/adapters/sandbox/image
```

It has Python 3.13 with pinned `sympy`, `numpy`, `scipy`, `matplotlib` and
`pandas`, a non-root user, no setuid binary, and the `Agg` matplotlib backend.

Then enable it in `config/sensai.toml` (the code default is off):

```toml
[sandbox]
enabled = true
image = "sensai-sandbox"
timeout = 30                # seconds
memory = "512m"
cpus = 1
artifacts_dir = "artifacts"
```

`artifacts_dir` is relative to the project. Limits must be positive, or the
config fails to load. At start-up, `app.py` checks that Docker answers and the
image exists; if not, it logs why (with the build command) and doesn't register
`run_python`. The rest of Sensai works as usual.

## The tool

`core/tools/builtin/python.py` registers `run_python`, with one argument,
`code`: the whole script. Its description tells the model what is installed,
to `print()` results, to save figures with `plt.savefig("name.png")`, that there
is no network or `input()`, and that each run starts fresh.

The tool sets `requires_confirmation=True` so human-in-the-loop approval can
gate it later; nothing enforces it yet.

The model reads the run as one text result:

```text
exit 1 in 0.4 s
--- stderr ---
Traceback (most recent call last):
  File "/work/main.py", line 1, in <module>
NameError: name 'x' is not defined
The code failed: read the error above, fix the code and call run_python again.
```

- The status line gives the exit code and duration, or `timed out after N s`.
- `stdout` keeps its start and `stderr` its end (where the traceback is), each
  capped at 4,000 characters.
- Saved files are listed under `--- files shown to the user ---`.
- A failed run is an error result ending with the fix-it line above.

## Self-correction

Nothing in the agent is specific to code. A failing run comes back as a tool
result with its traceback, so the ReAct loop's next thought sees the error and
calls `run_python` again with a fixed script. The loop's usual bounds
(thinking effort and the repeated-call guard) stop endless retries, and the
`react_thought` prompt asks to fix a failing call at most once.

## Running code

`DockerCodeRunner` (`adapters/sandbox/docker_runner.py`) implements the
`CodeRunner` port. For each call it:

1. writes the script as `main.py` in a fresh folder under
   `<artifacts_dir>/.work/`;
2. starts a container with only that folder mounted at `/work`;
3. waits up to `timeout`, then kills the container if it is still running;
4. reads `stdout` and `stderr` separately, and adds a note to `stderr` when the
   memory limit killed the script;
5. removes the container, whatever happened;
6. moves the files the script created, and a copy of the script, to
   `<artifacts_dir>/<YYYY-MM-DD>/<HHMMSS>-<id>/`.

Each container has no network, a read-only root filesystem with a 64 MB `/tmp`,
the memory (swap included), CPU and 128-process limits, the host user's uid and
no capabilities. If Docker itself fails, the runner raises `SandboxError`; an
error in the script is a normal, failed run.

## Tests

Unit tests use `FakeCodeRunner` (`tests/fakes/sandbox.py`) and need no Docker.
The live tests run against the real daemon and image, and are opt-in:

```bash
SENSAI_LIVE_SANDBOX=1 uv run pytest tests/adapters/sandbox/test_live.py
```

They check results, plots, tracebacks, the time and memory limits, no network,
the read-only image, the non-root user, and that no container is left behind.
