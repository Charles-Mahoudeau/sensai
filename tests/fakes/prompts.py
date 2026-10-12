"""Fake implementing the prompt repository port."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sensai.core.models.prompts import PromptVersion
from sensai.core.ports import PromptNotFoundError, PromptVersionNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sensai.core.ports import PromptRepository


def _ticking_clock() -> Callable[[], datetime]:
    """Return a clock that advances one second per call, so order is testable."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    counter = itertools.count()
    return lambda: start + timedelta(seconds=next(counter))


class InMemoryPromptRepository:
    """Keeps prompt versions and the active version of each prompt in dicts."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        """Start empty; `clock` supplies timestamps (deterministic by default)."""
        self._clock = clock or _ticking_clock()
        self._versions: dict[str, list[PromptVersion]] = {}
        self._active: dict[str, int] = {}

    async def create_version(
        self, name: str, content: str, *, note: str | None = None
    ) -> PromptVersion:
        """Save a new version, numbered after the latest one."""
        versions = self._versions.setdefault(name, [])
        prompt = PromptVersion(name, len(versions) + 1, content, self._clock(), note)
        versions.append(prompt)
        return prompt

    async def get_version(self, name: str, version: int) -> PromptVersion:
        """Return one version or raise `PromptVersionNotFoundError`."""
        versions = self._versions.get(name, [])
        if not 1 <= version <= len(versions):
            raise PromptVersionNotFoundError(
                f"prompt {name!r} has no version {version}"
            )
        return versions[version - 1]

    async def list_versions(self, name: str) -> Sequence[PromptVersion]:
        """Return every version of `name`, oldest first."""
        return list(self._versions.get(name, []))

    async def find_by_content(self, name: str, content: str) -> PromptVersion | None:
        """Return the latest version of `name` with exactly this content."""
        matches = [p for p in self._versions.get(name, []) if p.content == content]
        return matches[-1] if matches else None

    async def get_active(self, name: str) -> PromptVersion:
        """Return the active version or raise `PromptNotFoundError`."""
        if name not in self._active:
            raise PromptNotFoundError(f"prompt {name!r} has no active version")
        return await self.get_version(name, self._active[name])

    async def set_active(self, name: str, version: int) -> PromptVersion:
        """Make one version active, or raise `PromptVersionNotFoundError`."""
        prompt = await self.get_version(name, version)
        self._active[name] = version
        return prompt

    async def list_active(self) -> Sequence[PromptVersion]:
        """Return the active version of every prompt, ordered by name."""
        return [await self.get_active(name) for name in sorted(self._active)]


if TYPE_CHECKING:

    def _conforms(fake: InMemoryPromptRepository) -> PromptRepository:
        return fake
