"""Tests for the memories shown to the model in the system message."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sensai.core.agent.memory_recall import MemoryRecall, Recollection
from sensai.core.ports import StorageError
from tests.fakes.memory import InMemoryMemoryStore

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.memory import MemoryRecord


def _store(*facts: tuple[str, str]) -> InMemoryMemoryStore:
    """A store holding `(name, description)` facts, the last one most recent."""
    store = InMemoryMemoryStore()
    for name, description in facts:
        asyncio.run(store.create(name=name, type="preference", description=description))
    return store


def test_every_memory_is_shown_while_under_the_limit() -> None:
    """Each record is listed by name and description, most recent first."""
    store = _store(("voiture préférée", "Préfère les voitures BMW."), ("pseudo", ""))

    recollection = asyncio.run(MemoryRecall(store).recall("Qui suis-je ?"))

    assert recollection == Recollection(
        "What you remember about the user from earlier conversations:\n"
        "- pseudo\n"
        "- voiture préférée: Préfère les voitures BMW.",
        complete=True,
    )


def test_past_the_limit_the_relevant_memories_come_first() -> None:
    """The records matching the request win over the more recent ones."""
    store = _store(("car", "BMW"), ("language", "Rust"), ("editor", "Vim"))

    recollection = asyncio.run(
        MemoryRecall(store, limit=2).recall("Which car do I like?")
    )

    assert not recollection.complete
    assert recollection.text.splitlines()[1:] == [
        "- car: BMW",
        "- editor: Vim",
    ]


def test_nothing_stored_shows_nothing() -> None:
    """An empty store gives no block, and nothing is left to search."""
    recollection = asyncio.run(MemoryRecall(InMemoryMemoryStore()).recall("Hi"))

    assert recollection == Recollection("", complete=True)


class _BrokenStore(InMemoryMemoryStore):
    async def find(
        self, *, type: str | None = None, query: str | None = None
    ) -> Sequence[MemoryRecord]:
        raise StorageError("disk I/O error")


def test_a_storage_failure_shows_nothing() -> None:
    """The turn goes on without memories, and `memory_read` stays offered."""
    recollection = asyncio.run(MemoryRecall(_BrokenStore()).recall("Hi"))

    assert recollection == Recollection("", complete=False)
