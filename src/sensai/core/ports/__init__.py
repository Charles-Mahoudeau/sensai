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
    ProfileNotFoundError,
    SessionNotFoundError,
    SessionRepository,
    StorageError,
    UserProfileRepository,
)
from sensai.core.ports.repositories.prompts import (
    PromptNotFoundError,
    PromptRepository,
    PromptVersionNotFoundError,
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
    "ModelNotFoundError",
    "ProfileNotFoundError",
    "PromptNotFoundError",
    "PromptRepository",
    "PromptVersionNotFoundError",
    "RetrievalError",
    "SessionNotFoundError",
    "SessionRepository",
    "StorageError",
    "UserProfileRepository",
    "Vector",
    "VectorStore",
    "VectorStoreError",
]
