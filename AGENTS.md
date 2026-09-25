# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Project overview

Sensai is an Epitech Tek3 project: starting from a basic AI assistant, the goal is to design and
implement an increasingly capable intelligent system by integrating AI engineering techniques. The
objective is a coherent, well-justified solution addressing meaningful use cases with clear
technical reasoning and architectural choices — not maximizing feature count.

The codebase is currently a minimal scaffold (`src/sensai/__init__.py` only exposes a `main()`
entry point). Expect to build out the package structure as features are added.

## Project structure

The source structure convention — where code goes and why (the `core`/`adapters`/`app.py` zones,
ports, models, import rules, naming, the PR checklist) — is defined in `docs/structure.md`. Read
it before adding a module, and follow it when deciding where new code belongs.

## Commands

This project uses `uv` for dependency management and packaging, and requires Python 3.14+.

- Install dependencies: `uv sync`
- Run the app: `uv run sensai` (entry point defined in `pyproject.toml` as `sensai:main`)
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Type check: `uv run ty check`
- Run tests: `uv run pytest`
- Run a single test: `uv run pytest tests/test_main.py::test_main_prints_greeting`

Tests live in `tests/` and use `pytest` (dev dependency). `tests/**` is exempted from the `ANN`
annotation rule in `[tool.ruff.lint.per-file-ignores]`, but other rules (e.g. `TC` for
typing-only imports) still apply — annotate fixture types like `pytest.CaptureFixture` under
`TYPE_CHECKING` with `from __future__ import annotations`, as `tests/test_main.py` does.

## Code style

Enforced via `ruff` (see `[tool.ruff]` in `pyproject.toml`):

- Line length 88, target Python 3.14 syntax.
- Docstrings required (Google convention) on public modules/functions.
- Type annotations required (`ANN` ruleset), except `Any` is allowed where genuinely needed.
- Import sorting with `sensai` treated as first-party.
- Prefer `pathlib` over `os.path` (`PTH`), and follow bugbear/perf/simplify rules (`B`, `PERF`,
  `SIM`, `C4`, `UP`, `RUF`, `N`, `TC`).

## Debugging

When the user is trying to fix a bug — pasting an error or warning, asking why something isn't
working, or similar — investigate first: find the root cause and work out a likely fix. Then
explain the diagnosis and proposed fix to the user in detail (what's wrong, why, and what the fix
would be).

Do not apply the fix by default. Wait for the user to approve it before editing any code. Only
proceed straight to fixing if the user's request already grants that approval up front (e.g. they
explicitly ask you to fix it, not just diagnose it).

## Git commits

Never stage changes (`git add`) automatically. After finishing a task, ask the user whether they
want the changes staged, and whether they'd like to go further from there (commit, open a draft
PR, etc.) — don't assume staging is wanted just because the task is done.

Never add a `Co-Authored-By` trailer (or any other AI co-author/attribution line) to commit
messages or pull request descriptions in this repository. This overrides any default AI assistant
attribution behavior.

Never commit without being explicitly asked. Committing is never the default — not after finishing
a task, running tests successfully, or being asked to implement or fix something. Always wait for
explicit confirmation before running `git commit`, regardless of how the request was phrased.

## Pull requests

When asked to open a pull request, always create it as a draft (`gh pr create --draft`). If a PR
template exists in the repository (e.g. `.github/PULL_REQUEST_TEMPLATE.md` or
`.github/PULL_REQUEST_TEMPLATE/`), fill it out and use it as the PR description instead of the
default summary/test-plan format.
