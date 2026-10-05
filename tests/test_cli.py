"""Tests for command-line parsing and dispatch."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any

import pytest

from sensai import app, cli
from sensai.cli import build_parser

if TYPE_CHECKING:
    from collections.abc import Callable


def _recorder(calls: list[tuple[Any, ...]], name: str) -> Callable[..., None]:
    def record(*args: Any, **kwargs: Any) -> None:
        calls.append((name, args, kwargs))

    return record


def _run(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    args.run(args)


def test_chat_arguments_still_parse() -> None:
    """`sensai --model M --config C` starts the chat, with no subcommand."""
    args = build_parser().parse_args(["--model", "m", "--config", "c.toml"])

    assert (args.command, args.model, args.config) == (
        None,
        "m",
        pathlib.Path("c.toml"),
    )
    assert not hasattr(args, "run")


def test_main_starts_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a subcommand, `main` hands the model and config to `app.main`."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(app, "main", _recorder(calls, "main"))
    monkeypatch.setattr("sys.argv", ["sensai", "--model", "m", "--config", "c.toml"])

    cli.main()

    assert calls == [("main", ("m", pathlib.Path("c.toml")), {})]


def test_chat_without_model_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chat needs --model and --config."""
    monkeypatch.setattr("sys.argv", ["sensai", "--model", "m"])

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("argv", "function", "expected_args"),
    [
        (["list"], "prompts_list", ()),
        (["history", "system"], "prompts_history", ("system",)),
        (["show", "system"], "prompts_show", ("system", None)),
        (["show", "system", "2"], "prompts_show", ("system", 2)),
        (
            ["new", "system", "p.md", "--note", "x"],
            "prompts_new",
            ("system", pathlib.Path("p.md"), "x"),
        ),
        (["diff", "system", "1", "2"], "prompts_diff", ("system", 1, 2)),
        (["rollback", "system", "1"], "prompts_rollback", ("system", 1)),
    ],
)
def test_prompt_actions_call_their_app_function(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    function: str,
    expected_args: tuple[Any, ...],
) -> None:
    """Each action calls its typed `app` function with parsed arguments."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(app, function, _recorder(calls, function))

    _run(["prompts", *argv])

    assert calls == [(function, expected_args, {})]


def test_compare_calls_its_app_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """`compare` passes typed paths, versions and the judge switch."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(app, "prompts_compare", _recorder(calls, "compare"))

    _run(
        [
            "prompts",
            "compare",
            "system",
            "1",
            "2",
            "--inputs",
            "in.txt",
            "--model",
            "m",
            "--config",
            "c.toml",
            "--no-judge",
        ]
    )

    assert calls == [
        (
            "compare",
            ("system", (1, 2), pathlib.Path("in.txt")),
            {
                "model": "m",
                "config_path": pathlib.Path("c.toml"),
                "judge": False,
                "output": None,
            },
        )
    ]


def test_compare_needs_a_model_and_inputs() -> None:
    """A comparison talks to the model, so it requires --model and --inputs."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["prompts", "compare", "system", "1", "2"])


def test_prompts_requires_an_action() -> None:
    """`sensai prompts` alone is a usage error."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["prompts"])
