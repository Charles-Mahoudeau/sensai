"""Ollama implementation of the Embedder port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from sensai.adapters.ollama import _wire
from sensai.core.ports import (
    EmbedderUnavailableError,
    EmbeddingModelNotFoundError,
    RetrievalError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.ports import Embedder, Vector

DEFAULT_EMBED_MODEL = "nomic-embed-text"


class OllamaEmbedder:
    """Embeds texts with an Ollama server over HTTP."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str = DEFAULT_EMBED_MODEL,
    ) -> None:
        """Store the HTTP client, the server URL and the embedding model.

        Args:
            client: The HTTP client used for every request.
            base_url: The Ollama server URL, e.g. `http://localhost:11434`.
            model: The embedding model; defaults to `DEFAULT_EMBED_MODEL`.
        """
        self._client = client
        self._url = base_url.rstrip("/")
        self._model = model

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        """Embed several texts in one request, one vector per text."""
        if not texts:
            return []
        try:
            response = await self._client.post(
                f"{self._url}/api/embed",
                json={"model": self._model, "input": list(texts)},
            )
        except httpx.TransportError as e:
            raise EmbedderUnavailableError(
                f"cannot reach Ollama at {self._url}: {e}"
            ) from e

        if response.is_error:
            message = _wire.error_message(response.status_code, response.content)
            if response.status_code == httpx.codes.NOT_FOUND:
                raise EmbeddingModelNotFoundError(message)
            raise RetrievalError(message)

        return _vectors_from_response(response, expected=len(texts))


def _vectors_from_response(
    response: httpx.Response, expected: int
) -> list[list[float]]:
    try:
        body: Any = response.json()
    except ValueError as e:
        raise RetrievalError("Ollama returned invalid JSON for the embeddings") from e
    vectors = body.get("embeddings") if isinstance(body, dict) else None
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise RetrievalError(
            f"expected {expected} embeddings from Ollama, got {_describe(vectors)}"
        )
    return [[float(x) for x in vector] for vector in vectors]


def _describe(vectors: Any) -> str:
    return f"{len(vectors)}" if isinstance(vectors, list) else "none"


if TYPE_CHECKING:

    def _conforms(adapter: OllamaEmbedder) -> Embedder:
        return adapter
