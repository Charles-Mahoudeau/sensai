"""Format project-specific SQL continuation indentation."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PROJECT_ROOT = Path()
CONTINUATION = re.compile(r"^\s*(CHECK|DEFAULT|REFERENCES)\b")


def _format_sql(content: str) -> str:
    lines = content.splitlines(keepends=True)

    for index, line in enumerate(lines):
        if not CONTINUATION.match(line) or index == 0:
            continue

        previous = lines[index - 1].rstrip()
        if previous and not previous.endswith((",", "(")):
            lines[index] = f"        {line.lstrip()}"

    return "".join(lines)


def _sql_files(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(path.rglob("*.sql"))
        elif path.suffix == ".sql":
            files.add(path)
    return sorted(files)


def main() -> None:
    """Format SQL files or check whether they are already formatted."""
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, default=[PROJECT_ROOT])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    for path in _sql_files(args.paths):
        content = path.read_text()
        formatted = _format_sql(content)
        if formatted == content:
            continue
        changed.append(path)
        if not args.check:
            path.write_text(formatted)

    if args.check and changed:
        for path in changed:
            print(f"Would reformat: {path}")
        raise SystemExit(1)

    for path in changed:
        print(f"Reformatted: {path}")


if __name__ == "__main__":
    main()
