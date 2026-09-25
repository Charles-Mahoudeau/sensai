"""Interfaces the core needs from the outside world."""

from sensai.core.ports.llm import (
    LLM,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
    ModelNotFoundError,
)
from sensai.core.ports.memory import (
    DuplicateMemoryError,
    MemoryNotFoundError,
    MemoryStore,
    SessionNotFoundError,
    SessionStore,
    StorageError,
)
from sensai.core.ports.retrieval import (
    Embedder,
    EmbedderUnavailableError,
    EmbeddingModelNotFoundError,
    RetrievalError,
    Vector,
    VectorStore,
    VectorStoreError,
)

__all__ = [
    "LLM",
    "DuplicateMemoryError",
    "Embedder",
    "EmbedderUnavailableError",
    "EmbeddingModelNotFoundError",
    "LLMError",
    "LLMResponseError",
    "LLMUnavailableError",
    "MemoryNotFoundError",
    "MemoryStore",
    "ModelNotFoundError",
    "RetrievalError",
    "SessionNotFoundError",
    "SessionStore",
    "StorageError",
    "Vector",
    "VectorStore",
    "VectorStoreError",
]
