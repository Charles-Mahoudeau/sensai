"""Tests for the retrieval port contract, exercised through the fakes."""

from __future__ import annotations

import asyncio

import pytest

from sensai.core.models.retrieval.rag import Chunk
from sensai.core.ports import (
    EmbedderUnavailableError,
    EmbeddingModelNotFoundError,
    RetrievalError,
    VectorStoreError,
)
from tests.fakes import FakeEmbedder, InMemoryVectorStore

CATS = Chunk("c1", "cats purr", "pets", metadata={"lang": "en", "year": 2024})
DOGS = Chunk("c2", "dogs bark", "pets", metadata={"lang": "fr", "year": 2024})
CARS = Chunk("c3", "cars drive", "vehicles", metadata={"lang": "en", "year": 2020})


def _store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    asyncio.run(
        store.add([CATS, DOGS, CARS], [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]),
    )
    return store


def test_embedder_returns_one_vector_per_text_in_order() -> None:
    """Vectors come back in the order of the texts, and calls are recorded."""
    embedder = FakeEmbedder({"a": [1.0, 0.0], "b": [0.0, 1.0]})

    vectors = asyncio.run(embedder.embed(["b", "a"]))

    assert vectors == [[0.0, 1.0], [1.0, 0.0]]
    assert embedder.calls == [["b", "a"]]


def test_search_returns_most_similar_first_and_at_most_k() -> None:
    """Results are ordered by descending score and truncated to k."""
    results = asyncio.run(_store().search([1.0, 0.0], 2))

    assert [r.chunk.id for r in results] == ["c1", "c2"]
    assert results[0].score >= results[1].score


def test_search_filters_on_metadata() -> None:
    """Only chunks matching every key/value of `where` are considered."""
    results = asyncio.run(_store().search([1.0, 0.0], 5, where={"lang": "en"}))

    assert {r.chunk.id for r in results} == {"c1", "c3"}


def test_search_with_unknown_metadata_returns_nothing() -> None:
    """A filter no chunk satisfies gives an empty result, not an error."""
    assert asyncio.run(_store().search([1.0, 0.0], 5, where={"lang": "de"})) == []


def test_add_replaces_a_chunk_with_the_same_id() -> None:
    """Re-adding an id overwrites the previous chunk instead of duplicating it."""
    store = _store()
    updated = Chunk("c1", "cats meow", "pets")

    asyncio.run(store.add([updated], [[1.0, 0.0]]))
    results = asyncio.run(store.search([1.0, 0.0], 10))

    assert [r.chunk.text for r in results if r.chunk.id == "c1"] == ["cats meow"]
    assert len(results) == 3


def test_add_rejects_mismatched_lengths() -> None:
    """Chunks and vectors must line up one to one."""
    with pytest.raises(ValueError, match="same length"):
        asyncio.run(InMemoryVectorStore().add([CATS, DOGS], [[1.0, 0.0]]))


def test_delete_removes_every_chunk_of_a_document() -> None:
    """Deleting a document drops all its chunks and leaves the others."""
    store = _store()

    asyncio.run(store.delete("pets"))
    results = asyncio.run(store.search([1.0, 0.0], 10))

    assert [r.chunk.id for r in results] == ["c3"]


def test_delete_unknown_document_is_a_no_op() -> None:
    """Deleting a document that was never added does nothing."""
    store = _store()

    asyncio.run(store.delete("missing"))

    assert len(asyncio.run(store.search([1.0, 0.0], 10))) == 3


def test_retrieval_errors_share_a_base_class() -> None:
    """Callers can catch every retrieval failure with RetrievalError."""
    assert issubclass(EmbedderUnavailableError, RetrievalError)
    assert issubclass(EmbeddingModelNotFoundError, RetrievalError)
    assert issubclass(VectorStoreError, RetrievalError)
