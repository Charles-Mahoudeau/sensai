"""CLI entrypoint with argument parsing."""

import argparse
import pathlib

from sensai import app


def main() -> None:
    """The CLI entrypoint with argument parsing.

    Returns:
        None
    """
    parser = argparse.ArgumentParser(prog="sensai", description="An advanced AI agent.")

    parser.add_argument(
        "--model", help="the model identifier to use", type=str, required=True
    )
    parser.add_argument(
        "--config", help="the configuration file to use", type=str, required=True
    )

    args = parser.parse_args()

    app.main(args.model, pathlib.Path(args.config))
