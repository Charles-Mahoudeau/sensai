"""Minimal agent loop that streams one LLM response."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.core.errors import SensaiError
from sensai.core.ports import LLMError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.models import ChatEvent, Message
    from sensai.core.ports import LLM


class AgentError(SensaiError):
    """Raised when the agent cannot obtain a response from its LLM."""


# Implementation of a Runner that streams one LLM response
class Agent:
    """Stream one LLM response for the prepared conversation history."""

    def __init__(self, llm: LLM) -> None:
        """Initialize the agent with its chat model port."""
        self._llm = llm

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[ChatEvent]:
        """Relay LLM events and translate LLM failures to a core error."""
        try:
            async for event in self._llm.chat(messages):
                yield event  # Relay each event but keep function alive
        except LLMError as error:
            raise AgentError(str(error)) from error
