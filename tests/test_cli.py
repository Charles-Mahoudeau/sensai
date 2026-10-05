"""Tests for command-line parsing."""

from __future__ import annotations

import pathlib

import pytest

from sensai.cli import build_parser


def test_chat_arguments_still_parse() -> None:
    """`sensai --model M --config C` starts the chat, with no subcommand."""
    args = build_parser().parse_args(["--model", "m", "--config", "c.toml"])

    assert (args.command, args.model, args.config) == (None, "m", "c.toml")


def test_prompts_subcommands_parse() -> None:
    """Each prompt action parses its arguments with the right types."""
    parser = build_parser()

    show = parser.parse_args(["prompts", "show", "system"])
    rollback = parser.parse_args(["prompts", "rollback", "system", "2"])
    new = parser.parse_args(["prompts", "new", "system", "p.md", "--note", "x"])

    assert (show.action, show.name, show.version) == ("show", "system", None)
    assert (rollback.action, rollback.version) == ("rollback", 2)
    assert (new.file, new.note) == (pathlib.Path("p.md"), "x")


def test_compare_needs_a_model_and_inputs() -> None:
    """A comparison talks to the model, so it requires --model and --inputs."""
    parser = build_parser()

    args = parser.parse_args(
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

    assert (args.a, args.b, args.no_judge) == (1, 2, True)
    with pytest.raises(SystemExit):
        parser.parse_args(["prompts", "compare", "system", "1", "2"])


def test_prompts_requires_an_action() -> None:
    """`sensai prompts` alone is a usage error."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["prompts"])
