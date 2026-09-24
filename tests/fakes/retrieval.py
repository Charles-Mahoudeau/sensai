"""Fakes implementing the retrieval ports."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from sensai.core.models.retrieval.rag import ScoredChunk

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models.retrieval.rag import Chunk, Metadata
    from sensai.core.ports import Embedder, Vector, VectorStore


class FakeEmbedder:
    """Returns pre-defined vectors and records every call.

    Texts are looked up in `vectors`; an unknown text fails loudly so a test
    never silently embeds something it didn't script.
    """

    def __init__(self, vectors: Mapping[str, Vector]) -> None:
        """Store the text-to-vector table."""
        self._vectors = vectors
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        """Record the request and return the scripted vector of each text."""
        self.calls.append(list(texts))
        missing = [text for text in texts if text not in self._vectors]
        if missing:
            raise KeyError(f"FakeEmbedder has no vector for {missing!r}")
        return [self._vectors[text] for text in texts]


class InMemoryVectorStore:
    """A brute-force cosine-similarity store that keeps everything in a dict."""

    def __init__(self) -> None:
        """Start with an empty store."""
        self._items: dict[str, tuple[Chunk, Vector]] = {}

    async def add(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None:
        """Insert chunks, replacing any chunk with the same id."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._items[chunk.id] = (chunk, vector)

    async def search(
        self,
        vector: Vector,
        k: int,
        *,
        where: Metadata | None = None,
    ) -> Sequence[ScoredChunk]:
        """Return the `k` most similar chunks that match the metadata filter."""
        scored = [
            ScoredChunk(chunk, _cosine(vector, stored))
            for chunk, stored in self._items.values()
            if where is None or _matches(chunk.metadata, where)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:k]

    async def delete(self, document_id: str) -> None:
        """Remove every chunk of a document."""
        self._items = {
            chunk_id: (chunk, vector)
            for chunk_id, (chunk, vector) in self._items.items()
            if chunk.document_id != document_id
        }


def _matches(metadata: Metadata, where: Metadata) -> bool:
    return all(
        key in metadata and metadata[key] == value for key, value in where.items()
    )


def _cosine(a: Vector, b: Vector) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


if TYPE_CHECKING:

    def _embedder_conforms(fake: FakeEmbedder) -> Embedder:
        return fake

    def _store_conforms(fake: InMemoryVectorStore) -> VectorStore:
        return fake
