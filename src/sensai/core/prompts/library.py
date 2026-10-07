"""Versioning rules for named prompts: sync, activate, roll back, diff."""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from sensai.core.ports import PromptNotFoundError
from sensai.core.prompts.comparison import ComparisonError
from sensai.core.prompts.defaults import JUDGE, SYSTEM
from sensai.core.prompts.rules import validate

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models.prompts import PromptVersion
    from sensai.core.ports import PromptRepository
    from sensai.core.prompts.comparison import ComparisonReport, PromptComparison

DEFAULT_NOTE = "default from code"

# A comparison sends each version as the system message: only prompts used that
# way in the chat give meaningful results.
COMPARABLE = frozenset({SYSTEM})


class PromptLibrary:
    """Manages the versions of every prompt and which one is active."""

    def __init__(self, repo: PromptRepository) -> None:
        """Use `repo` to store versions."""
        self._repo = repo

    async def sync_defaults(self, defaults: Mapping[str, str]) -> list[PromptVersion]:
        """Store the code defaults that the repository doesn't know yet.

        A default whose exact text has no stored version becomes a new version
        and is activated. A default that is already stored changes nothing, so
        a rollback to an older version survives restarts.

        Args:
            defaults: The default text of each prompt, keyed by name.

        Returns:
            The versions created by this call.

        Raises:
            InvalidPromptError: A default breaks its prompt's rule.
        """
        created: list[PromptVersion] = []
        for name, content in defaults.items():
            validate(name, content)
            if await self._repo.find_by_content(name, content) is not None:
                continue
            prompt = await self._repo.create_version(name, content, note=DEFAULT_NOTE)
            await self._repo.set_active(name, prompt.version)
            created.append(prompt)
        return created

    async def active(self, name: str) -> PromptVersion:
        """Return the active version of a prompt.

        Raises:
            PromptNotFoundError: The prompt has no active version.
        """
        return await self._repo.get_active(name)

    async def system_prompt(self, profile: str = "") -> str:
        """Return the chat's system message: active `system` prompt + profile.

        The parts are joined with a blank line and not stripped. That is how
        Ollama joins consecutive system messages, so the model reads exactly
        what it read when the agent sent its own system message.

        Args:
            profile: The rendered user profile; omitted when empty.

        Raises:
            PromptNotFoundError: No version of `system` is active.
        """
        base = (await self._repo.get_active(SYSTEM)).content
        return "\n\n".join(part for part in (base, profile) if part)

    async def active_all(self) -> Sequence[PromptVersion]:
        """Return the active version of every prompt, ordered by name."""
        return await self._repo.list_active()

    async def history(self, name: str) -> Sequence[PromptVersion]:
        """Return every version of a prompt, oldest first.

        Raises:
            PromptNotFoundError: The prompt has no version.
        """
        versions = await self._repo.list_versions(name)
        if not versions:
            raise PromptNotFoundError(f"unknown prompt {name!r}")
        return versions

    async def get(self, name: str, version: int | None = None) -> PromptVersion:
        """Return one version of a prompt, or its active version if `None`.

        Raises:
            PromptNotFoundError: `version` is `None` and nothing is active.
            PromptVersionNotFoundError: The prompt has no such version.
        """
        if version is None:
            return await self._repo.get_active(name)
        return await self._repo.get_version(name, version)

    async def new_version(
        self, name: str, content: str, *, note: str | None = None
    ) -> PromptVersion:
        """Save `content` as the active version of a prompt.

        Content identical to a stored version re-activates that version instead
        of creating a duplicate.

        Raises:
            InvalidPromptError: `content` breaks the prompt's rule, e.g. a
                placeholder the code fills in is missing.
        """
        validate(name, content)
        prompt = await self._repo.find_by_content(name, content)
        if prompt is None:
            prompt = await self._repo.create_version(name, content, note=note)
        return await self._repo.set_active(name, prompt.version)

    async def rollback(self, name: str, version: int) -> PromptVersion:
        """Make an existing version of a prompt the active one again.

        Raises:
            PromptVersionNotFoundError: The prompt has no such version.
        """
        return await self._repo.set_active(name, version)

    async def diff(self, name: str, old: int, new: int) -> str:
        """Return a unified diff from version `old` to version `new`.

        Raises:
            PromptVersionNotFoundError: The prompt has no such version.
        """
        before = await self._repo.get_version(name, old)
        after = await self._repo.get_version(name, new)
        return "".join(
            difflib.unified_diff(
                before.content.splitlines(keepends=True),
                after.content.splitlines(keepends=True),
                fromfile=f"{name} v{old}",
                tofile=f"{name} v{new}",
            )
        )

    async def compare(
        self,
        comparison: PromptComparison,
        name: str,
        versions: tuple[int, int],
        inputs: Sequence[str],
        *,
        judge: bool,
    ) -> ComparisonReport:
        """Compare two versions of a prompt on the same inputs.

        Args:
            comparison: Runs the versions against the model.
            name: The prompt to compare; only prompts in `COMPARABLE`.
            versions: The two version numbers.
            inputs: The user messages both versions answer.
            judge: Whether the active `judge` prompt also rates the answers.

        Raises:
            ComparisonError: The prompt can't be compared, or `inputs` is empty.
            PromptVersionNotFoundError: The prompt has no such version.
        """
        if name not in COMPARABLE:
            allowed = ", ".join(sorted(COMPARABLE))
            raise ComparisonError(
                f"prompt {name!r} can't be compared: a comparison sends each "
                f"version as the system message, which only fits {allowed}"
            )
        a = await self._repo.get_version(name, versions[0])
        b = await self._repo.get_version(name, versions[1])
        judge_prompt = (await self._repo.get_active(JUDGE)).content if judge else None
        return await comparison.compare(a, b, inputs, judge_prompt=judge_prompt)
