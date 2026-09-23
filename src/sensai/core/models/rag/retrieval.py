from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias, Mapping

Metadata: TypeAlias = Mapping[str, str | int | float | bool]

@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    text: str
    doc_source: str
    index: int = 0 # position dans le document source (peut etre définir une taille max dans le chunker)
    # aussi ca peut servir a prendre les chunks autour d'un pertinent
    metadata: Metadata = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Chunk.id must be a non-empty string")
        if self.index < 0:
            raise ValueError("Chunk.index must be a non-negative integer")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float # a définir la norme de scoring pour la pertinence des données
