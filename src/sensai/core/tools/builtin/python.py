"""Tool running Python code in the sandbox, for math and plots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolOutput, ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import CodeRunner
    from sensai.core.tools.registry import ToolHandler, ToolRegistry

NAME = "run_python"


def register_self(tool_registry: ToolRegistry, runner: CodeRunner) -> None:
    """Register `run_python`, backed by `runner`."""
    tool_registry.register(spec(), handler(runner))


def spec() -> ToolSpec:
    """Describe the tool to the model."""
    return ToolSpec(
        name=NAME,
        description=(
            "Runs a Python 3 script in an isolated sandbox and returns what it "
            "prints. Use it to compute: solve equations, simplify, integrate, "
            "do numerics or statistics, and to draw plots. sympy, numpy, scipy, "
            "matplotlib and pandas are installed. print() every result you need. "
            'Save each figure with plt.savefig("name.png"): saved files are shown '
            "to the user. No network, no input(), and each run starts fresh, so "
            "send the whole script every time. If it fails, read the traceback, "
            "fix the code and call the tool again."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The full Python script."}
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        requires_confirmation=True,
    )


def handler(runner: CodeRunner) -> ToolHandler:
    """Build the registry handler that runs the given code."""

    async def run_python(arguments: Mapping[str, Any]) -> ToolOutput:
        code = arguments.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("'code' must be a non-empty Python script")
        run = await runner.run(code)
        return ToolOutput(
            run.stdout + run.stderr, attachments=run.artifacts, is_error=not run.ok
        )

    return run_python
