"""Minimal agent loop that streams one LLM response."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sensai.core.agent.events import (
    AgentEvent,
    ToolRunFinished,
    ToolRunStarted,
    TurnCompleted,
)
from sensai.core.errors import SensaiError
from sensai.core.models import Message, TextDelta, ToolCall
from sensai.core.models.llm import ToolCallRequest
from sensai.core.ports import LLMError
from sensai.core.tools.builtin import web_search
from sensai.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.ports import LLM


class AgentError(SensaiError):
    """Raised when the agent cannot get a response from its LLM."""


# Implementation of a Runner that streams one LLM response
class Agent:
    """Stream one LLM response for the prepared conversation history."""

    def __init__(self, llm: LLM) -> None:
        """Initialize the agent with its chat model port."""
        self._llm = llm
        self._tool_registry = ToolRegistry()
        web_search.register_self(self._tool_registry)
        self._max_tool_calls = 10
        self._logger = logging.getLogger("Agent")

    async def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Relay LLM events and translate LLM failures to a core error."""
        working = list(messages)
        produced: list[Message] = []

        try:
            for _ in range(self._max_tool_calls):
                text_parts: list[str] = []
                calls: list[ToolCall] = []

                async for event in self._llm.chat(
                    working, tools=self._tool_registry.spec()
                ):
                    match event:
                        case TextDelta(text=text):
                            text_parts.append(text)
                            yield event  # stream only tokens
                        case ToolCallRequest(call=call):
                            calls.append(call)

                # Save assistant message
                assistant = Message.assistant(
                    "".join(text_parts), tool_calls=tuple(calls)
                )
                working.append(assistant)
                produced.append(assistant)

                if not calls:
                    break

                # Run tools
                for call in calls:
                    yield ToolRunStarted(call)
                    result = await self._tool_registry.call(call)
                    yield ToolRunFinished(call, result)
                    working.append(
                        Message.tool(result.content, result.name, result.call_id)
                    )
                    produced.append(
                        Message.tool(result.content, result.name, result.call_id)
                    )
            else:
                raise RuntimeError("maximum number of tool calls reached")

            yield TurnCompleted(produced)
        except LLMError as error:
            raise AgentError(str(error)) from error
