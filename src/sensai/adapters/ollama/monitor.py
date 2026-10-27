"""Ollama implementation of the ModelMonitor port."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from sensai.adapters.ollama import _wire
from sensai.core.ports import LLMResponseError, LLMUnavailableError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.llm import LoadedModel
    from sensai.core.ports import ModelMonitor

DEFAULT_TIMEOUT = 5.0


class OllamaMonitor:
    """Reads the models an Ollama server has loaded, through `/api/ps`."""

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
            timeout: Seconds to wait for `/api/ps`. It overrides the client's
                timeout, which is often disabled for slow chat answers.
        """
        self._client = client
        self._url = base_url.rstrip("/")
        self._timeout = timeout

    async def loaded_models(self) -> Sequence[LoadedModel]:
        """List the models currently loaded, with their memory footprint."""
        try:
            response = await self._client.get(
                f"{self._url}/api/ps", timeout=self._timeout
            )
        except httpx.TransportError as e:
            raise LLMUnavailableError(f"cannot reach Ollama at {self._url}: {e}") from e

        if response.is_error:
            raise LLMResponseError(
                _wire.error_message(response.status_code, response.content)
            )
        try:
            body = response.json()
        except ValueError as e:
            raise LLMResponseError("Ollama returned invalid JSON for /api/ps") from e
        return _wire.loaded_models_from_body(body)


if TYPE_CHECKING:

    def _conforms(adapter: OllamaMonitor) -> ModelMonitor:
        return adapter
