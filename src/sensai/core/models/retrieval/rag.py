"""Immutable models used by document retrieval pipelines."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

type Metadata = Mapping[str, str | int | float | bool]


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable piece of a document."""

    id: str
    text: str
    document_id: str
    index: int = 0
    metadata: Metadata = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        """Validate the chunk identity and position."""
        if not self.id:
            raise ValueError("Chunk.id must be a non-empty string")
        if self.index < 0:
            raise ValueError("Chunk.index must be a non-negative integer")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk paired with its retrieval relevance score."""

    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class Document:
    """A source document before it is split into chunks."""

    id: str
    text: str
    source: str
    metadata: Metadata = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        """Validate the document identity and freeze its metadata."""
        if not self.id:
            raise ValueError("Document.id must be a non-empty string")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
