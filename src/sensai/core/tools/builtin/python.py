"""Tool running Python code in the sandbox, for math and plots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.models import ToolOutput, ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.models.sandbox import CodeRun
    from sensai.core.ports import CodeRunner
    from sensai.core.tools.registry import ToolHandler, ToolRegistry

NAME = "run_python"
OUTPUT_LIMIT = 4000
"""Most characters of stdout, and of stderr, given back to the model."""

_FIX_IT = (
    "The code failed: read the error above, fix the code and call run_python again."
)


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
        return format_run(await runner.run(code))

    return run_python


def format_run(run: CodeRun) -> ToolOutput:
    """Turn a run into the text the model reads, with its files attached."""
    if run.timed_out:
        status = f"timed out after {run.duration:.0f} s"
    else:
        status = f"exit {run.exit_code} in {run.duration:.1f} s"
    parts = [status]
    if run.stdout:
        parts.append(f"--- stdout ---\n{_cap(run.stdout, keep_end=False)}")
    if run.stderr:
        parts.append(f"--- stderr ---\n{_cap(run.stderr, keep_end=True)}")
    if run.artifacts:
        files = "\n".join(f"{a.path} ({a.media_type})" for a in run.artifacts)
        parts.append(f"--- files shown to the user ---\n{files}")
    if not run.ok:
        parts.append(_FIX_IT)
    return ToolOutput("\n".join(parts), attachments=run.artifacts, is_error=not run.ok)


def _cap(text: str, *, keep_end: bool) -> str:
    """Shorten `text` to `OUTPUT_LIMIT` characters, keeping its start or its end.

    A traceback's useful part is at its end; printed results start at the top.
    """
    if len(text) <= OUTPUT_LIMIT:
        return text
    cut = len(text) - OUTPUT_LIMIT
    if keep_end:
        return f"[… {cut} characters cut]\n{text[-OUTPUT_LIMIT:]}"
    return f"{text[:OUTPUT_LIMIT]}\n[… {cut} characters cut]"
