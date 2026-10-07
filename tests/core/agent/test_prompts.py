"""Tests for the ReAct prompts given to the agent."""

from __future__ import annotations

import asyncio

from sensai.core.agent.prompts import AgentPrompts
from sensai.core.prompts import PromptLibrary, load_defaults
from tests.fakes import InMemoryPromptRepository


def test_defaults_are_the_shipped_react_prompts() -> None:
    """`defaults()` reads the three ReAct defaults from the code."""
    texts = load_defaults()

    prompts = AgentPrompts.defaults()

    assert prompts == AgentPrompts(
        thought=texts["react_thought"],
        notes=texts["react_notes"],
        answer=texts["react_answer"],
    )


def test_active_uses_the_active_versions() -> None:
    """`active()` follows the library, rollbacks included."""

    async def run() -> AgentPrompts:
        library = PromptLibrary(InMemoryPromptRepository())
        await library.sync_defaults(load_defaults())
        await library.new_version("react_answer", "Answer briefly.")
        await library.new_version("react_answer", "Answer at length.")
        await library.rollback("react_answer", 2)
        return await AgentPrompts.active(library)

    prompts = asyncio.run(run())

    assert prompts.answer == "Answer briefly."
    assert prompts.thought == load_defaults()["react_thought"]
