"""Ollama implementation of the ModelMonitor port."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from sensai.adapters.ollama import _wire
from sensai.core.ports import LLMResponseError, LLMUnavailableError, ModelNotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.llm import LoadedModel
    from sensai.core.ports import ModelMonitor

DEFAULT_TIMEOUT = 5.0


class OllamaMonitor:
    """Reads what an Ollama server has loaded (`/api/ps`) and model details."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Store the HTTP client, the server URL and the request timeout.

        Args:
            client: The HTTP client used for every request.
            base_url: The Ollama server URL, e.g. `http://localhost:11434`.
            timeout: Seconds to wait for each request. It overrides the client's
                timeout, which is often disabled for slow chat answers.
        """
        self._client = client
        self._url = base_url.rstrip("/")
        self._timeout = timeout

    async def loaded_models(self) -> Sequence[LoadedModel]:
        """List the models currently loaded, with their memory footprint."""
        body = await self._request("GET", "/api/ps")
        return _wire.loaded_models_from_body(body)

    async def max_context_length(self, model: str) -> int | None:
        """Read the model's trained context window from `/api/show`."""
        body = await self._request("POST", "/api/show", {"model": model})
        return _wire.max_context_from_show(body)

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        try:
            response = await self._client.request(
                method, f"{self._url}{path}", json=payload, timeout=self._timeout
            )
        except httpx.TransportError as e:
            raise LLMUnavailableError(f"cannot reach Ollama at {self._url}: {e}") from e

        if response.is_error:
            message = _wire.error_message(response.status_code, response.content)
            if response.status_code == httpx.codes.NOT_FOUND:
                raise ModelNotFoundError(message)
            raise LLMResponseError(message)
        try:
            return response.json()
        except ValueError as e:
            raise LLMResponseError(f"Ollama returned invalid JSON for {path}") from e


if TYPE_CHECKING:

    def _conforms(adapter: OllamaMonitor) -> ModelMonitor:
        return adapter
