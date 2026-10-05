"""Tests for the prompt versioning rules."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.ports import PromptNotFoundError, PromptVersionNotFoundError
from sensai.core.prompts import InvalidPromptError, PromptLibrary
from sensai.core.prompts.library import DEFAULT_NOTE
from tests.fakes import InMemoryPromptRepository

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def _run(scenario: Callable[[PromptLibrary], Awaitable[None]]) -> None:
    asyncio.run(scenario(PromptLibrary(InMemoryPromptRepository())))


def test_sync_stores_and_activates_new_defaults() -> None:
    """A default the repository doesn't know becomes the active v1."""

    async def scenario(library: PromptLibrary) -> None:
        created = await library.sync_defaults({"system": "Be helpful."})

        active = await library.active("system")
        assert [p.version for p in created] == [1]
        assert (active.version, active.content, active.note) == (
            1,
            "Be helpful.",
            DEFAULT_NOTE,
        )

    _run(scenario)


def test_sync_twice_changes_nothing() -> None:
    """Syncing the same defaults again creates no version."""

    async def scenario(library: PromptLibrary) -> None:
        await library.sync_defaults({"system": "Be helpful."})

        assert await library.sync_defaults({"system": "Be helpful."}) == []
        assert len(await library.history("system")) == 1

    _run(scenario)


def test_changed_default_becomes_a_new_active_version() -> None:
    """Editing a default in the code creates and activates the next version."""

    async def scenario(library: PromptLibrary) -> None:
        await library.sync_defaults({"system": "Be helpful."})

        await library.sync_defaults({"system": "Be concise."})

        assert (await library.active("system")).version == 2

    _run(scenario)


def test_rollback_survives_a_sync() -> None:
    """A default that is already stored doesn't undo a rollback."""

    async def scenario(library: PromptLibrary) -> None:
        await library.sync_defaults({"system": "Be helpful."})
        await library.new_version("system", "Be concise.", note="shorter")

        await library.rollback("system", 1)
        await library.sync_defaults({"system": "Be helpful."})

        assert (await library.active("system")).version == 1

    _run(scenario)


def test_new_version_with_known_content_reactivates_it() -> None:
    """Saving content identical to an old version doesn't duplicate it."""

    async def scenario(library: PromptLibrary) -> None:
        await library.new_version("system", "Be helpful.")
        await library.new_version("system", "Be concise.")

        prompt = await library.new_version("system", "Be helpful.")

        assert prompt.version == 1
        assert (await library.active("system")).version == 1
        assert len(await library.history("system")) == 2

    _run(scenario)


def test_get_defaults_to_the_active_version() -> None:
    """Without a version number, `get` returns the active version."""

    async def scenario(library: PromptLibrary) -> None:
        await library.new_version("system", "Be helpful.")
        await library.new_version("system", "Be concise.")
        await library.rollback("system", 1)

        assert (await library.get("system")).version == 1
        assert (await library.get("system", 2)).content == "Be concise."

    _run(scenario)


def test_diff_shows_the_changed_lines() -> None:
    """The diff is a unified diff labelled with both versions."""

    async def scenario(library: PromptLibrary) -> None:
        await library.new_version("system", "Hello.\nBe helpful.\n")
        await library.new_version("system", "Hello.\nBe concise.\n")

        diff = await library.diff("system", 1, 2)

        assert "--- system v1" in diff
        assert "+++ system v2" in diff
        assert "-Be helpful.\n" in diff
        assert "+Be concise.\n" in diff
        assert " Hello.\n" in diff

    _run(scenario)


def test_diff_of_identical_versions_is_empty() -> None:
    """Diffing a version with itself returns an empty string."""

    async def scenario(library: PromptLibrary) -> None:
        await library.new_version("system", "Be helpful.")

        assert await library.diff("system", 1, 1) == ""

    _run(scenario)


def test_unknown_prompt_and_version_raise() -> None:
    """Unknown prompts and versions raise the port's errors."""

    async def scenario(library: PromptLibrary) -> None:
        await library.new_version("system", "Be helpful.")

        with pytest.raises(PromptNotFoundError):
            await library.history("missing")
        with pytest.raises(PromptNotFoundError):
            await library.active("missing")
        with pytest.raises(PromptVersionNotFoundError):
            await library.rollback("system", 9)

    _run(scenario)


def test_new_version_that_breaks_its_rule_is_rejected() -> None:
    """A thought prompt without `{tools}` is refused and nothing is stored."""

    async def scenario(library: PromptLibrary) -> None:
        await library.new_version("react_thought", "{tools} ready to answer")

        with pytest.raises(InvalidPromptError):
            await library.new_version("react_thought", "Just think.")

        assert len(await library.history("react_thought")) == 1
        assert (await library.active("react_thought")).version == 1

    _run(scenario)


def test_invalid_default_fails_the_sync() -> None:
    """A broken shipped default fails at startup, not in the middle of a chat."""

    async def scenario(library: PromptLibrary) -> None:
        with pytest.raises(InvalidPromptError):
            await library.sync_defaults({"react_notes": "no placeholder"})

    _run(scenario)
