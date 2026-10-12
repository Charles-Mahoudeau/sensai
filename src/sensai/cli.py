"""CLI entrypoint with argument parsing."""

import argparse
import pathlib

from sensai import app

type _Commands = argparse._SubParsersAction[argparse.ArgumentParser]


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the chat and the developer subcommands.

    Without a subcommand, `sensai` starts the chat. Each subcommand stores the
    function that runs it as `run`.

    Returns:
        The argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="sensai",
        description="An advanced AI agent.",
        parents=[_model_options(required=False)],
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    _add_prompts_commands(commands)
    return parser


def _model_options(*, required: bool) -> argparse.ArgumentParser:
    """Options for commands that talk to the model."""
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument(
        "--model", required=required, help="the model identifier to use"
    )
    options.add_argument(
        "--config",
        type=pathlib.Path,
        required=required,
        help="the configuration file to use",
    )
    return options


def _add_prompts_commands(commands: _Commands) -> None:
    """Add `sensai prompts <action>`."""
    prompts = commands.add_parser("prompts", help="manage versioned prompts")
    actions = prompts.add_subparsers(dest="action", metavar="ACTION", required=True)

    list_ = actions.add_parser("list", help="list prompts and their active version")
    list_.set_defaults(run=lambda _: app.prompts_list())

    history = actions.add_parser("history", help="list every version of a prompt")
    history.add_argument("name")
    history.set_defaults(run=lambda a: app.prompts_history(a.name))

    show = actions.add_parser(
        "show", help="print a version (the active one by default)"
    )
    show.add_argument("name")
    show.add_argument("version", type=int, nargs="?")
    show.set_defaults(run=lambda a: app.prompts_show(a.name, a.version))

    new = actions.add_parser("new", help="save a file as the new active version")
    new.add_argument("name")
    new.add_argument("file", type=pathlib.Path)
    new.add_argument("--note", help="what changed in this version")
    new.set_defaults(run=lambda a: app.prompts_new(a.name, a.file, a.note))

    diff = actions.add_parser("diff", help="show the changes between two versions")
    diff.add_argument("name")
    diff.add_argument("old", type=int)
    diff.add_argument("new", type=int)
    diff.set_defaults(run=lambda a: app.prompts_diff(a.name, a.old, a.new))

    rollback = actions.add_parser("rollback", help="make an older version active")
    rollback.add_argument("name")
    rollback.add_argument("version", type=int)
    rollback.set_defaults(run=lambda a: app.prompts_rollback(a.name, a.version))

    compare = actions.add_parser(
        "compare",
        help="run two versions on the same inputs and compare them",
        parents=[_model_options(required=True)],
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
    compare.add_argument(
        "--no-judge", action="store_true", help="skip the LLM judge (metrics only)"
    )
    compare.add_argument(
        "--output", type=pathlib.Path, help="save the full report as JSON"
    )
    compare.set_defaults(
        run=lambda a: app.prompts_compare(
            a.name,
            (a.a, a.b),
            a.inputs,
            model=a.model,
            config_path=a.config,
            judge=not a.no_judge,
            output=a.output,
        )
    )


def main() -> None:
    """The CLI entrypoint with argument parsing.

    Returns:
        None
    """
    parser = build_parser()
    args = parser.parse_args()

    if (run := getattr(args, "run", None)) is not None:
        run(args)
        return

    if args.model is None or args.config is None:
        parser.error("--model and --config are required to start the chat")

    app.main(args.model, args.config)
