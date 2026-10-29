# ADR: Sandbox mechanism for code execution

- **Status:** accepted
- **Issue:** #52 (part of #51, [T2] Sandboxed Code Execution)

## Context

Sensai is aimed at mathematicians. To compute exact results (solve, simplify,
integrate), run numerics and draw plots, the model writes Python and Sensai runs
it. That code comes from a language model: it can be wrong, loop forever,
allocate too much memory, or, through a prompt injection in a fetched page, try
to read files or reach the network. It must run somewhere it can't hurt the
user's machine or data.

Two mechanisms were compared:

- **Isolated subprocess:** `python` started by Sensai, limited with `resource`
  rlimits, a timeout and a temporary working folder.
- **Docker container:** one fresh container per run, from an image with the math
  stack, driven by the Docker SDK for Python.

## Comparison

| Criterion | Isolated subprocess | Docker container |
|---|---|---|
| Isolation | Same user, same kernel view: the code sees the user's files, environment variables and processes. | Own filesystem, processes and user; every capability dropped. |
| Network | Open. Closing it needs OS-specific tools (namespaces, firewall rules). | `network_mode="none"`: no interface but loopback. |
| Filesystem | Can read and write anything the user can. A temporary folder is only a convention. | Read-only image; only the run folder (`/work`) and a 64 MB `/tmp` are writable. |
| Limits | rlimits are Unix-only and partial (no reliable memory cap on macOS, none on Windows). | Memory (swap included), CPUs and process count enforced by cgroups; memory kills are reported (`OOMKilled`). |
| Dependencies | The math stack must be installed in the user's environment, at matching versions. | Pinned in the image: same versions for everyone. |
| Setup cost | None. | Docker installed and running, plus one `docker build` (image ≈ 580 MB). |
| Latency | Lowest (Python start-up only). | ≈ 0.35 s for `print(1)`, ≈ 0.7 s with `sympy`, ≈ 1.3 s with `matplotlib` (measured locally, warm image). |

## Decision

**Run code in a fresh Docker container per call**, through the Docker SDK for
Python (`adapters/sandbox/docker_runner.py`), behind the `CodeRunner` port.

A subprocess can't keep model-written code away from the user's files or the
network without OS-specific work that would end up rebuilding a container. The
setup cost is one `docker build`, already familiar to the team, and the
latency is small next to a local model's generation time.

Each run uses:

- no network, a read-only root filesystem, and a small `/tmp` tmpfs;
- only its run folder mounted, at `/work`;
- memory (swap included), CPU and process limits, and a time limit after which
  the container is killed;
- the host user's uid, every capability dropped, and an image without setuid
  binaries;
- removal of the container whatever the outcome.

## Consequences

- Without Docker or the image, `run_python` isn't registered: Sensai logs why
  (with the build command) and the rest still works.
- Each call starts from a clean state: no variables are kept between runs. The
  model sends a whole script each time.
- Run folders live under the artifacts directory, not `/tmp`: snap-packaged
  Docker has its own private `/tmp`, and Docker Desktop only shares some host
  folders.
- `no-new-privileges` is not set: under snap-packaged Docker with AppArmor it
  stops Python from starting. Stripping setuid/setgid bits from the image, a
  non-root user and dropping every capability cover the same risk.
- The core never imports the Docker SDK (import-linter contract): another
  runner, such as a remote one, can replace it behind `CodeRunner`.
