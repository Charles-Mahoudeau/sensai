"""Tests for the terminal output of the prompt commands."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from rich.console import Console

from sensai.adapters.cli import PromptCommands
from sensai.core.models import ChatDone, TextDelta
from sensai.core.models.llm import Usage
from sensai.core.prompts import PromptComparison, PromptLibrary
from tests.fakes import FakeLLM, InMemoryPromptRepository

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable


def _run(scenario: Callable[[PromptCommands, Console], Awaitable[None]]) -> str:
    """Run a scenario on a library holding system v1 (active) and v2."""
    console = Console(record=True, width=120, color_system=None)

    async def run() -> None:
        library = PromptLibrary(InMemoryPromptRepository())
        await library.sync_defaults({"system": "Be helpful.\n", "judge": "Judge."})
        await library.new_version("system", "Be concise.\n", note="shorter")
        await library.rollback("system", 1)
        await scenario(PromptCommands(library, console), console)

    asyncio.run(run())
    return console.export_text()


def test_list_shows_active_versions() -> None:
    """Every prompt is listed with its active version and version count."""

    async def scenario(commands: PromptCommands, _: Console) -> None:
        await commands.list()

    output = _run(scenario)

    system_row = next(line for line in output.splitlines() if "system" in line)
    assert "v1" in system_row
    assert "2" in system_row
    assert "judge" in output


def test_history_marks_the_active_version() -> None:
    """The active version has a marker; notes are shown."""

    async def scenario(commands: PromptCommands, _: Console) -> None:
        await commands.history("system")

    lines = _run(scenario).splitlines()

    assert "●" in next(line for line in lines if "v1" in line)
    assert "●" not in next(line for line in lines if "v2" in line)
    assert any("shorter" in line for line in lines)


def test_show_prints_content_and_state() -> None:
    """`show` prints a header and the raw content of the version."""

    async def scenario(commands: PromptCommands, _: Console) -> None:
        await commands.show("system", 2)

    output = _run(scenario)

    assert "system v2" in output
    assert "(active)" not in output
    assert "Be concise." in output


def test_diff_and_rollback_messages() -> None:
    """`diff` prints changed lines; `rollback` says what was active before."""

    async def scenario(commands: PromptCommands, _: Console) -> None:
        await commands.diff("system", 1, 2)
        await commands.rollback("system", 2)

    output = _run(scenario)

    assert "-Be helpful." in output
    assert "+Be concise." in output
    assert "system v2 is now active (was v1)" in output


def test_new_reads_the_file(tmp_path: pathlib.Path) -> None:
    """`new` saves the file's content as the active version."""
    path = tmp_path / "v3.md"
    path.write_text("Be precise.\n", encoding="utf-8")

    async def scenario(commands: PromptCommands, _: Console) -> None:
        await commands.new("system", path, "precision")
        await commands.show("system", None)

    output = _run(scenario)

    assert "system v3 is now active" in output
    assert "Be precise." in output


def test_compare_prints_summary_and_saves_json(tmp_path: pathlib.Path) -> None:
    """The summary table is printed and the full report is written as JSON."""
    inputs = tmp_path / "inputs.txt"
    inputs.write_text("first question\n\nsecond question\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    answer = [TextDelta("ok"), ChatDone(Usage(completion_tokens=3, prompt_tokens=1))]
    verdict = [TextDelta('{"winner": "tie", "reason": "same"}')]
    llm = FakeLLM([answer, answer, verdict, verdict] * 2)
    ticks = iter(float(n) for n in range(100))

    async def scenario(commands: PromptCommands, _: Console) -> None:
        await commands.compare(
            PromptComparison(llm, lambda: next(ticks)),
            "system",
            (1, 2),
            inputs,
            judge=True,
            output=report_path,
        )

    output = _run(scenario)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "system comparison" in output
    assert "Judge wins" in output
    assert "2 tie(s) out of 2 inputs" in output
    assert [r["input"] for r in report["results"]] == [
        "first question",
        "second question",
    ]
