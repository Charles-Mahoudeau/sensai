"""Port for chat language models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.models.llm import ChatEvent, ChatOptions, Message
    from sensai.core.models.tools import ToolSpec


class LLMError(Exception):
    """Base class for every error raised by an LLM adapter."""


class LLMUnavailableError(LLMError):
    """The model server cannot be reached."""


class ModelNotFoundError(LLMError):
    """The requested model does not exist on the model server."""


class LLMResponseError(LLMError):
    """The model server returned a response that cannot be understood."""


class LLM(Protocol):
    """A chat model that streams its answer as core events."""

    def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        options: ChatOptions | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Stream the model's answer to a conversation.

        The stream yields text, thinking and tool-call events in generation
        order, and ends with exactly one `ChatDone`.

        Args:
            messages: The conversation history, oldest first.
            tools: The tools the model is allowed to call.
            options: Generation parameters; `None` keeps the model defaults.

        Raises:
            LLMUnavailableError: The model server cannot be reached.
            ModelNotFoundError: The requested model does not exist.
            LLMResponseError: The server's response cannot be understood.
        """
        ...
