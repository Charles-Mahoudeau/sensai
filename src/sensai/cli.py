"""CLI entrypoint with argument parsing."""

import argparse
import pathlib

from sensai import app


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the chat and the developer subcommands.

    Returns:
        The argument parser.
    """
    parser = argparse.ArgumentParser(prog="sensai", description="An advanced AI agent.")

    parser.add_argument("--model", help="the model identifier to use", type=str)
    parser.add_argument("--config", help="the configuration file to use", type=str)

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    prompts = commands.add_parser("prompts", help="manage versioned prompts")
    actions = prompts.add_subparsers(dest="action", metavar="ACTION", required=True)

    actions.add_parser("list", help="list prompts and their active version")

    history = actions.add_parser("history", help="list every version of a prompt")
    history.add_argument("name")

    show = actions.add_parser(
        "show", help="print a version (the active one by default)"
    )
    show.add_argument("name")
    show.add_argument("version", type=int, nargs="?")

    new = actions.add_parser("new", help="save a file as the new active version")
    new.add_argument("name")
    new.add_argument("file", type=pathlib.Path)
    new.add_argument("--note", help="what changed in this version")

    diff = actions.add_parser("diff", help="show the changes between two versions")
    diff.add_argument("name")
    diff.add_argument("old", type=int)
    diff.add_argument("new", type=int)

    rollback = actions.add_parser("rollback", help="make an older version active")
    rollback.add_argument("name")
    rollback.add_argument("version", type=int)

    compare = actions.add_parser(
        "compare", help="run two versions on the same inputs and compare them"
    )
    compare.add_argument("name")
    compare.add_argument("a", type=int)
    compare.add_argument("b", type=int)
    compare.add_argument(
        "--inputs",
        type=pathlib.Path,
        required=True,
        help="a text file with one input per line",
    )
    compare.add_argument("--model", required=True, help="the model identifier to use")
    compare.add_argument("--config", required=True, help="the configuration file")
    compare.add_argument(
        "--no-judge", action="store_true", help="skip the LLM judge (metrics only)"
    )
    compare.add_argument(
        "--output", type=pathlib.Path, help="save the full report as JSON"
    )

    return parser


def main() -> None:
    """The CLI entrypoint with argument parsing.

    Returns:
        None
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "prompts":
        app.run_prompts(args)
        return

    if args.model is None or args.config is None:
        parser.error("--model and --config are required to start the chat")

    app.main(args.model, pathlib.Path(args.config))
