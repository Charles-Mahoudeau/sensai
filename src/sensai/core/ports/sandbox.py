"""Port for running untrusted code in isolation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from sensai.core.models.sandbox import CodeRun


class SandboxError(SensaiError):
    """The sandbox could not run the code at all (not an error in the code)."""


class CodeRunner(Protocol):
    """Runs a Python script in an isolated, short-lived environment."""

    async def run(self, code: str) -> CodeRun:
        """Run `code` and return what it printed, its exit status and its files.

        An exception or a timeout inside the script is a `CodeRun`, not an error.

        Raises:
            SandboxError: The sandbox itself failed, e.g. it is unavailable.
        """
        ...
