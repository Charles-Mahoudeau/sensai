"""Ollama implementation of the LLM port."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from sensai.adapters.ollama import _wire
from sensai.core.models.llm import ChatDone
from sensai.core.ports import LLMResponseError, LLMUnavailableError, ModelNotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from sensai.core.models.llm import ChatEvent, ChatOptions, Message
    from sensai.core.models.tools import ToolSpec
    from sensai.core.ports import LLM


class OllamaChat:
    """Streams chat completions from an Ollama server over HTTP.

    The client should have a short connect timeout and no read timeout, because
    a model can stay silent for a long time before its first token.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        *,
        new_call_id: Callable[[], str] = _wire.new_call_id,
    ) -> None:
        """Store the HTTP client, the server URL and the model name.

        Args:
            client: The HTTP client used for every request.
            base_url: The Ollama server URL, e.g. `http://localhost:11434`.
            model: The model to chat with.
            new_call_id: Makes an id for tool calls that Ollama did not identify.
        """
        self._client = client
        self._url = base_url.rstrip("/")
        self._model = model
        self._new_call_id = new_call_id

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        options: ChatOptions | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Stream the model's answer to a conversation."""
        payload = _wire.chat_payload(self._model, messages, tools, options)
        try:
            async with self._client.stream(
                "POST", f"{self._url}/api/chat", json=payload
            ) as response:
                if response.status_code >= 400:
                    message = _wire.error_message(
                        response.status_code, await response.aread()
                    )
                    if response.status_code == 404:
                        raise ModelNotFoundError(message)
                    raise LLMResponseError(message)

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = _wire.decode_chunk(line)
                    for event in _wire.events_from_chunk(chunk, self._new_call_id):
                        yield event
                        if isinstance(event, ChatDone):
                            return
        except httpx.TransportError as e:
            raise LLMUnavailableError(f"cannot reach Ollama at {self._url}: {e}") from e
        raise LLMResponseError("the Ollama stream ended without a final 'done' message")


if TYPE_CHECKING:

    def _conforms(adapter: OllamaChat) -> LLM:
        return adapter
