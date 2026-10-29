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
