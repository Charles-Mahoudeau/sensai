"""Database script."""

import argparse
import sys

from sensai.adapters.storage import sqlite_migrator
from sensai.adapters.storage.connection import create_connection


def _nuke(args: argparse.Namespace) -> None:
    if not args.yes:
        ok_input = input("Are you sure you want to nuke the database? (y/N) ")
        if ok_input.lower() != "y":
            print("Aborted")
            raise SystemExit(1)
    sqlite_migrator.nuke_database()
    print("Database nuked")


def _migrations_new(args: argparse.Namespace) -> None:
    path = sqlite_migrator.create_migration(args.name)
    print(f"Migration created at {path}")


def _migrations_apply(args: argparse.Namespace) -> None:
    try:
        sqlite_migrator.apply_migrations(create_connection())
    except Exception as e:
        print(f"Error applying migrations: {e}")
        raise SystemExit(1) from None
    print("Migrations applied")


def _migrations_status(args: argparse.Namespace) -> None:
    try:
        state = sqlite_migrator.check_migrations_state(create_connection())
    except Exception as e:
        print(f"Error checking migrations: {e}")
        raise SystemExit(1) from None
    if state:
        print("Migrations are up to date")
    else:
        print("Migrations are out of date")
        raise SystemExit(1) from None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sensai-db", description="Manage database and migrations."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_nuke = sub.add_parser("nuke", help="nuke the database")
    p_nuke.add_argument("-y", "--yes", action="store_true", help="confirm nuke")
    p_nuke.set_defaults(func=_nuke)

    p_migrations = sub.add_parser("migrations", help="manage database migrations")
    migrations_sub = p_migrations.add_subparsers(dest="action", required=True)

    p_migrations_new = migrations_sub.add_parser("new", help="create a new migration")
    p_migrations_new.add_argument("name", help="name of the new migration")
    p_migrations_new.set_defaults(func=_migrations_new)

    p_migrations_apply = migrations_sub.add_parser(
        "apply", help="apply pending migrations"
    )
    p_migrations_apply.set_defaults(func=_migrations_apply)

    p_migrations_status = migrations_sub.add_parser(
        "status", help="show status of migrations"
    )
    p_migrations_status.set_defaults(func=_migrations_status)

    return parser


def main() -> None:
    """The CLI entrypoint with argument parsing.

    Returns:
        None
    """
    parser = _build_parser()
    args = parser.parse_args()

    if not args.func:
        print("error: command not implemented", file=sys.stderr)
        raise SystemExit(1)

    args.func(args)


if __name__ == "__main__":
    main()
