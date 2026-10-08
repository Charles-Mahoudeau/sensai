"""Terminal output for the `sensai prompts` developer commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from pathlib import Path

    from sensai.core.models.prompts import PromptVersion
    from sensai.core.prompts import ComparisonReport, PromptComparison, PromptLibrary


def _date(prompt: PromptVersion) -> str:
    return prompt.created_at.strftime("%Y-%m-%d %H:%M")


class PromptCommands:
    """Runs one prompt command against the library and prints its result."""

    def __init__(self, library: PromptLibrary, console: Console | None = None) -> None:
        """Print to `console`, or to the terminal by default."""
        self._library = library
        self._console = console or Console()

    async def list(self) -> None:
        """Print every prompt with its active version."""
        table = Table("Prompt", "Active", "Versions", "Created", "Note")
        for prompt in await self._library.active_all():
            versions = await self._library.history(prompt.name)
            table.add_row(
                prompt.name,
                f"v{prompt.version}",
                str(len(versions)),
                _date(prompt),
                prompt.note or "",
            )
        self._console.print(table)

    async def history(self, name: str) -> None:
        """Print every version of a prompt, marking the active one."""
        active = await self._library.active(name)
        table = Table("", "Version", "Created", "Note", title=name)
        for prompt in await self._library.history(name):
            marker = "●" if prompt.version == active.version else ""
            table.add_row(
                marker, f"v{prompt.version}", _date(prompt), prompt.note or ""
            )
        self._console.print(table)

    async def show(self, name: str, version: int | None) -> None:
        """Print one version of a prompt, the active one by default."""
        prompt = await self._library.get(name, version)
        active = await self._library.active(name)
        state = " (active)" if prompt.version == active.version else ""
        note = f" · {prompt.note}" if prompt.note else ""
        self._console.print(
            f"[bold]{name} v{prompt.version}[/bold]{state} · {_date(prompt)}{note}"
        )
        self._console.print(prompt.content, markup=False, highlight=False)

    async def new(self, name: str, path: Path, note: str | None) -> None:
        """Save the content of a file as the active version of a prompt."""
        prompt = await self._library.new_version(
            name, path.read_text(encoding="utf-8"), note=note
        )
        self._console.print(f"{name} v{prompt.version} is now active")

    async def diff(self, name: str, old: int, new: int) -> None:
        """Print a unified diff between two versions."""
        diff = await self._library.diff(name, old, new)
        if not diff:
            self._console.print(f"{name} v{old} and v{new} are identical")
            return
        self._console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))

    async def rollback(self, name: str, version: int) -> None:
        """Make an older version active again."""
        previous = await self._library.active(name)
        await self._library.rollback(name, version)
        self._console.print(
            f"{name} v{version} is now active (was v{previous.version})"
        )

    async def compare(
        self,
        comparison: PromptComparison,
        name: str,
        versions: tuple[int, int],
        inputs: Path,
        *,
        judge: bool,
        output: Path | None,
    ) -> None:
        """Run a comparison and print its summary; save it as JSON if asked.

        `inputs` holds one input per line; blank lines are skipped.
        """
        lines = inputs.read_text(encoding="utf-8").splitlines()
        texts = [line.strip() for line in lines if line.strip()]
        with self._console.status(
            f"Comparing {name} v{versions[0]} and v{versions[1]}"
            f" on {len(texts)} inputs…"
        ):
            report = await self._library.compare(
                comparison, name, versions, texts, judge=judge
            )
        self._print_report(report)
        if output is not None:
            output.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
            self._console.print(f"Report saved to {output}")

    def _print_report(self, report: ComparisonReport) -> None:
        a, b = report.a, report.b
        table = Table(
            "", f"v{a.version}", f"v{b.version}", title=f"{report.name} comparison"
        )
        table.add_row(
            "Mean latency", f"{a.mean_latency:.2f} s", f"{b.mean_latency:.2f} s"
        )
        table.add_row(
            "Mean completion tokens",
            f"{a.mean_completion_tokens:.0f}",
            f"{b.mean_completion_tokens:.0f}",
        )
        table.add_row(
            "Mean answer length",
            f"{a.mean_length:.0f} chars",
            f"{b.mean_length:.0f} chars",
        )
        if report.judged:
            table.add_row("Judge wins", str(a.wins), str(b.wins))
            table.caption = f"{report.ties} tie(s) out of {len(report.results)} inputs"
        self._console.print(table)
