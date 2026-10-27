"""Tests for OllamaMonitor, using httpx.MockTransport instead of a real server."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx
import pytest

from sensai.adapters.ollama import OllamaMonitor
from sensai.core.models.llm import LoadedModel
from sensai.core.ports import (
    LLMResponseError,
    LLMUnavailableError,
    ModelNotFoundError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

type Handler = Callable[[httpx.Request], httpx.Response]


def _loaded_models(handler: Handler, **kwargs: float) -> Sequence[LoadedModel]:
    async def run() -> Sequence[LoadedModel]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=None
        ) as client:
            monitor = OllamaMonitor(client, "http://ollama:11434/", **kwargs)
            return await monitor.loaded_models()

    return asyncio.run(run())


def _json(body: object, status: int = 200) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def test_loaded_models_come_from_api_ps() -> None:
    """Each entry of `/api/ps` becomes a LoadedModel."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen3:8b",
                        "size": 6_000,
                        "size_vram": 4_000,
                        "context_length": 8192,
                        "expires_at": "2026-10-27T12:00:00Z",
                    }
                ]
            },
        )

    models = _loaded_models(handler)

    (request,) = seen
    assert request.method == "GET"
    assert request.url == "http://ollama:11434/api/ps"
    assert models == [
        LoadedModel(
            name="qwen3:8b", size_bytes=6_000, vram_bytes=4_000, context_length=8192
        )
    ]


def test_no_loaded_model_is_an_empty_list() -> None:
    """An idle server has unloaded everything."""
    assert _loaded_models(_json({"models": []})) == []


def test_connection_refused_is_unavailable() -> None:
    """A refused connection becomes LLMUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailableError, match="cannot reach Ollama"):
        _loaded_models(handler)


def test_request_has_its_own_timeout() -> None:
    """`/api/ps` gets a timeout even when the client has none."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"models": []})

    _loaded_models(handler, timeout=2.0)

    assert seen[0].extensions["timeout"]["read"] == 2.0


def test_timeout_is_unavailable() -> None:
    """A server that does not answer in time is reported as unavailable."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(LLMUnavailableError, match="cannot reach Ollama"):
        _loaded_models(handler)


def test_http_error_keeps_the_server_message() -> None:
    """A failed request becomes LLMResponseError with Ollama's message."""
    with pytest.raises(LLMResponseError, match="boom"):
        _loaded_models(_json({"error": "boom"}, status=500))


def test_invalid_json_is_a_response_error() -> None:
    """A body that is not JSON is reported."""
    handler: Handler = lambda _request: httpx.Response(200, content=b"not json")  # noqa: E731

    with pytest.raises(LLMResponseError, match="invalid JSON"):
        _loaded_models(handler)


def _max_context(handler: Handler) -> int | None:
    async def run() -> int | None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=None
        ) as client:
            monitor = OllamaMonitor(client, "http://ollama:11434")
            return await monitor.max_context_length("llama3.2:3B")

    return asyncio.run(run())


def test_max_context_comes_from_api_show() -> None:
    """The model name is posted to `/api/show`, with the monitor's timeout."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model_info": {
                    "general.architecture": "llama",
                    "llama.context_length": 131_072,
                }
            },
        )

    assert _max_context(handler) == 131_072
    (request,) = seen
    assert request.method == "POST"
    assert request.url == "http://ollama:11434/api/show"
    assert json.loads(request.content) == {"model": "llama3.2:3B"}
    assert request.extensions["timeout"]["read"] == 5.0


def test_unknown_model_is_model_not_found() -> None:
    """HTTP 404 from `/api/show` becomes ModelNotFoundError."""
    with pytest.raises(ModelNotFoundError, match="not found"):
        _max_context(_json({"error": "model 'x' not found"}, status=404))
