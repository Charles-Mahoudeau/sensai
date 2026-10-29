"""Immutable models for code run in a sandbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from sensai.core.models.tools import Attachment


@dataclass(frozen=True, slots=True)
class CodeRun:
    """The outcome of running a script in the sandbox.

    Attributes:
        stdout: What the script printed.
        stderr: Its error output, tracebacks included.
        exit_code: The process exit code; 0 means success.
        duration: Seconds the run took.
        timed_out: Whether the run was stopped at the time limit.
        artifacts: The files the script created, saved for the user.
        script: Where the executed script was saved, if it was.
    """

    stdout: str
    stderr: str
    exit_code: int
    duration: float
    timed_out: bool = False
    artifacts: tuple[Attachment, ...] = ()
    script: Path | None = None

    @property
    def ok(self) -> bool:
        """Tell whether the script ran to the end without an error."""
        return self.exit_code == 0 and not self.timed_out
