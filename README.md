# Sensai

## Description

Starting from a basic AI assistant, you will design and implement an increasingly capable intelligent system by integrating advanced AI engineering techniques. Your objective is not to maximize the number of features, but to create a coherent, well-justified solution that addresses meaningful use cases while demonstrating clear technical reasoning and architectural choices.

## Requirements

* Python 3.14+
* [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
```

## Usage

```bash
uv run sensai
```

## Development

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
uv run ty check        # type check
uv run pytest          # run tests
```

### Pre-commit hooks

This repo uses [pre-commit](https://pre-commit.com/) to run lint, format, and type checks
before each commit, and the test suite before each push. Install the hooks once after cloning:

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

To run all hooks manually against the full codebase:

```bash
uv run pre-commit run --all-files
uv run pre-commit run --all-files --hook-stage pre-push
```

## Authors

* Charles Mahoudeau - ``charles.mahoudeau@epitech.eu``
* Matthieu Coraleau - ``matthieu.coraleau@epitech.eu``
* Noé Caillaud - ``noe.caillaud@epitech.eu``
* Tristan Fragnaud - ``tristan.fragnaud@epitech.eu``
