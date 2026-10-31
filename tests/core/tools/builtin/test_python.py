"""Tests for the run_python tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sensai.core.models import Attachment, ToolCall, ToolResult
from sensai.core.models.sandbox import CodeRun
from sensai.core.tools.builtin import python
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeCodeRunner

PLOT = Attachment(Path("artifacts/run/plot.png"), "image/png")


def _call(runner: FakeCodeRunner, code: object = "print(1)") -> ToolResult:
    registry = ToolRegistry()
    python.register_self(registry, runner)
    return asyncio.run(registry.call(ToolCall(python.NAME, {"code": code}, id="c1")))


def test_the_code_is_run_and_its_files_attached() -> None:
    """The script goes to the sandbox; its output and files come back."""
    runner = FakeCodeRunner([CodeRun("[2, 3]\n", "", 0, 1.0, artifacts=(PLOT,))])

    result = _call(runner, "print(solve(x**2 - 5*x + 6))")

    assert runner.codes == ["print(solve(x**2 - 5*x + 6))"]
    assert not result.is_error
    assert "[2, 3]" in result.content
    assert result.attachments == (PLOT,)


def test_a_failing_run_is_an_error() -> None:
    """A run that isn't ok marks the result as failed, traceback included."""
    result = _call(FakeCodeRunner([CodeRun("", "NameError: y", 1, 0.2)]))

    assert result.is_error
    assert "NameError: y" in result.content


def test_the_status_and_sections_are_labelled() -> None:
    """The model reads the exit status, then each labelled section."""
    run = CodeRun("x = 2\n", "warning\n", 0, 1.25, artifacts=(PLOT,))
    content = python.format_run(run).content

    assert content.startswith("exit 0 in 1.2 s\n--- stdout ---\nx = 2")
    assert "--- stderr ---\nwarning" in content
    assert (
        "--- files shown to the user ---\nartifacts/run/plot.png (image/png)" in content
    )
    assert "fix the code" not in content


def test_a_failure_asks_the_model_to_fix_and_retry() -> None:
    """A failed run ends with the instruction to correct the code."""
    output = python.format_run(CodeRun("", "NameError: y", 1, 0.4))

    assert output.is_error
    assert output.content.startswith("exit 1 in 0.4 s")
    assert output.content.endswith("fix the code and call run_python again.")


def test_a_timeout_says_so() -> None:
    """A run stopped at the limit reports the timeout, as a failure."""
    output = python.format_run(CodeRun("", "", -1, 30.0, timed_out=True))

    assert output.is_error
    assert output.content.startswith("timed out after 30 s")


def test_long_outputs_keep_the_useful_end() -> None:
    """Stdout keeps its start; stderr keeps its end, where the error is."""
    long_out = "a" * 5000 + "END_OF_STDOUT"
    long_err = "START_OF_STDERR" + "b" * 5000 + "ValueError: boom"
    content = python.format_run(CodeRun(long_out, long_err, 1, 1.0)).content

    assert "END_OF_STDOUT" not in content
    assert "START_OF_STDERR" not in content
    assert "ValueError: boom" in content
    assert content.count("characters cut") == 2


@pytest.mark.parametrize("code", ["", "   ", None, 42])
def test_missing_code_is_refused_without_running(code: object) -> None:
    """Invalid arguments come back as an error; the sandbox is not called."""
    runner = FakeCodeRunner([])

    result = _call(runner, code)

    assert result.is_error
    assert runner.codes == []


def test_the_tool_is_marked_for_confirmation() -> None:
    """Running code will need approval once human-in-the-loop exists."""
    assert python.spec().requires_confirmation
