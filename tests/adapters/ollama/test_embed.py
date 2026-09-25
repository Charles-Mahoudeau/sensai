"""Tests for OllamaEmbedder, using httpx.MockTransport instead of a real server."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx
import pytest

from sensai.adapters.ollama import DEFAULT_EMBED_MODEL, OllamaEmbedder
from sensai.core.ports import (
    EmbedderUnavailableError,
    EmbeddingModelNotFoundError,
    RetrievalError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sensai.core.ports import Vector

type Handler = Callable[[httpx.Request], httpx.Response]


def _embed(handler: Handler, texts: Sequence[str], **kwargs: str) -> Sequence[Vector]:
    async def run() -> Sequence[Vector]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaEmbedder(client, "http://ollama:11434", **kwargs).embed(
                texts
            )

    return asyncio.run(run())


def _json(body: object, status: int = 200) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def test_vectors_come_back_in_the_order_of_the_texts() -> None:
    """One plain Python vector per text, in order."""
    handler = _json({"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    assert _embed(handler, ["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_integer_values_are_returned_as_floats() -> None:
    """Vectors are always lists of floats."""
    vectors = _embed(_json({"embeddings": [[1, 2]]}), ["a"])

    assert vectors == [[1.0, 2.0]]
    assert all(isinstance(x, float) for x in vectors[0])


def test_the_whole_batch_is_sent_in_one_request() -> None:
    """Texts go to `/api/embed` together, with the default model."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"embeddings": [[1.0], [2.0]]})

    _embed(handler, ["a", "b"])

    (request,) = seen
    assert request.url == "http://ollama:11434/api/embed"
    assert json.loads(request.content) == {
        "model": DEFAULT_EMBED_MODEL,
        "input": ["a", "b"],
    }


def test_default_model_is_the_standard_ollama_embedding_model() -> None:
    """The fallback model is `nomic-embed-text`."""
    assert DEFAULT_EMBED_MODEL == "nomic-embed-text"


def test_model_can_be_changed() -> None:
    """A caller can choose another embedding model."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    _embed(handler, ["a"], model="mxbai-embed-large")

    assert json.loads(seen[0].content)["model"] == "mxbai-embed-large"


def test_empty_input_makes_no_request() -> None:
    """Nothing to embed means nothing is sent."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert _embed(handler, []) == []


def test_connection_refused_is_unavailable() -> None:
    """A refused connection becomes EmbedderUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EmbedderUnavailableError, match="cannot reach Ollama"):
        _embed(handler, ["a"])


def test_unknown_model_is_model_not_found() -> None:
    """HTTP 404 becomes EmbeddingModelNotFoundError with the server's message."""
    handler = _json(
        {"error": 'model "nope" not found, try pulling it first'}, status=404
    )

    with pytest.raises(EmbeddingModelNotFoundError, match="try pulling it first"):
        _embed(handler, ["a"])


def test_other_http_errors_are_retrieval_errors() -> None:
    """A 500 keeps the server's message in a RetrievalError."""
    with pytest.raises(RetrievalError, match="out of memory"):
        _embed(_json({"error": "out of memory"}, status=500), ["a"])


def test_malformed_responses_are_retrieval_errors() -> None:
    """A missing key, a wrong count or invalid JSON is reported."""
    bad_bodies = [{}, {"embeddings": None}, {"embeddings": [[1.0]]}, {"embeddings": []}]
    for body in bad_bodies:
        with pytest.raises(RetrievalError, match="expected 2 embeddings"):
            _embed(_json(body), ["a", "b"])

    invalid_json: Handler = lambda _request: httpx.Response(200, content=b"not json")  # noqa: E731
    with pytest.raises(RetrievalError, match="invalid JSON"):
        _embed(invalid_json, ["a"])
