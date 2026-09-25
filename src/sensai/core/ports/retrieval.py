"""Ports for embedding models and vector stores."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.retrieval.rag import Chunk, Metadata, ScoredChunk

type Vector = Sequence[float]


class RetrievalError(Exception):
    """Base class for every error raised by an embedder or a vector store."""


class EmbedderUnavailableError(RetrievalError):
    """The embedding server cannot be reached."""


class EmbeddingModelNotFoundError(RetrievalError):
    """The requested embedding model does not exist on the server."""


class VectorStoreError(RetrievalError):
    """The vector store failed to read or write its data."""


class Embedder(Protocol):
    """Turns texts into vectors that can be compared by similarity."""

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        """Embed several texts in one call.

        Args:
            texts: The texts to embed.

        Returns:
            One vector per text, in the same order. All vectors have the same
            length.

        Raises:
            EmbedderUnavailableError: The embedding server cannot be reached.
            EmbeddingModelNotFoundError: The embedding model does not exist.
        """
        ...


class VectorStore(Protocol):
    """Stores chunks with their vectors and finds the most similar ones."""

    async def add(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None:
        """Insert chunks, replacing any chunk that has the same id.

        Args:
            chunks: The chunks to store.
            vectors: One vector per chunk, in the same order.

        Raises:
            ValueError: `chunks` and `vectors` have different lengths.
            VectorStoreError: The store failed to write.
        """
        ...

    async def search(
        self,
        vector: Vector,
        k: int,
        *,
        where: Metadata | None = None,
    ) -> Sequence[ScoredChunk]:
        """Find the chunks most similar to a vector.

        Args:
            vector: The query vector.
            k: The maximum number of chunks to return.
            where: Only consider chunks whose metadata contains every one of
                these key/value pairs; `None` considers every chunk.

        Returns:
            At most `k` chunks, most similar first. A higher score means more
            similar.

        Raises:
            VectorStoreError: The store failed to read.
        """
        ...

    async def delete(self, document_id: str) -> None:
        """Remove every chunk that belongs to a document.

        Does nothing when the document is unknown, so a document can be
        re-ingested by deleting it and adding its new chunks.

        Args:
            document_id: The `Chunk.document_id` to remove.

        Raises:
            VectorStoreError: The store failed to write.
        """
        ...
