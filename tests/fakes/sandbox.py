"""Fake implementing the code runner port."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.sandbox import CodeRun
    from sensai.core.ports import CodeRunner


class FakeCodeRunner:
    """Returns one scripted run per call and records the code it was given."""

    def __init__(self, runs: Sequence[CodeRun]) -> None:
        """Store the runs to return, in order."""
        self._runs = iter(runs)
        self.codes: list[str] = []

    async def run(self, code: str) -> CodeRun:
        """Record `code`, then return the next scripted run."""
        self.codes.append(code)
        return next(self._runs)


if TYPE_CHECKING:

    def _conforms(fake: FakeCodeRunner) -> CodeRunner:
        return fake
