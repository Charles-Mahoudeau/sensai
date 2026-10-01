"""Interfaces the core needs from the outside world."""

from sensai.core.ports.llm import (
    LLM,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
    ModelNotFoundError,
)
from sensai.core.ports.repositories.memory import (
    DuplicateMemoryError,
    MemoryNotFoundError,
    MemoryRepository,
    UserProfileRepository,
    ProfileNotFoundError,
    SessionNotFoundError,
    SessionRepository,
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
    "MemoryRepository",
    "UserProfileRepository",
    "ModelNotFoundError",
    "ProfileNotFoundError",
    "RetrievalError",
    "SessionNotFoundError",
    "SessionRepository",
    "StorageError",
    "Vector",
    "VectorStore",
    "VectorStoreError",
]
