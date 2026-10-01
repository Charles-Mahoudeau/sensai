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
from sensai.core.models.llm import ThinkingDelta, ToolCallRequest
from sensai.core.ports import LLMError
from sensai.core.tools.builtin import web_search
from sensai.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.ports import LLM


class AgentError(SensaiError):
    """Raised when the agent cannot get a response from its LLM."""


class AgentRun:
    """Stores the data of an agent run."""

    def __init__(self, messages: Sequence[Message]) -> None:
        """Start a run from the prepared conversation history."""
        self._working_messages: list[Message] = list(messages)
        self._produced_messages: list[Message] = []

    @property
    def messages(self) -> list[Message]:
        """Return the full conversation used for the next LLM call."""
        return self._working_messages

    @property
    def produced_messages(self) -> list[Message]:
        """Return the messages to persist once the turn completes."""
        return self._produced_messages

    def add_message(self, message: Message, *, final: bool = True) -> None:
        """Append a message, keeping it in the produced ones if final."""
        self._working_messages.append(message)
        if final:
            self._produced_messages.append(message)

    def clone(self) -> AgentRun:
        """Return a new run started from the current working messages."""
        return AgentRun(self.messages)


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
        run = AgentRun(messages)

        try:
            async for event in self._loop(run):
                yield event
        except LLMError as error:
            raise AgentError(str(error)) from error

    async def _run_tool_calls(
        self, run: AgentRun, tool_calls: Sequence[ToolCall]
    ) -> AsyncIterator[AgentEvent]:
        for call in tool_calls:
            yield ToolRunStarted(call=call)
            result = await self._tool_registry.call(call)
            yield ToolRunFinished(call=call, result=result)
            run.add_message(Message.tool(result.content, result.name, result.call_id))

    async def _loop(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        for _ in range(self._max_tool_calls):
            text_parts: list[str] = []
            calls: list[ToolCall] = []

            async for event in self._llm.chat(
                run.messages, tools=self._tool_registry.spec()
            ):
                match event:
                    case TextDelta(text=text):
                        text_parts.append(text)
                        yield event
                    case ThinkingDelta():
                        yield event  # display only, not kept in the history
                    case ToolCallRequest(call=call):
                        calls.append(call)

            # Save assistant message
            assistant = Message.assistant("".join(text_parts), tool_calls=tuple(calls))
            run.add_message(assistant)

            if not calls:
                break

            # Run tools
            async for event in self._run_tool_calls(run, calls):
                yield event

        else:
            raise RuntimeError("maximum number of tool calls reached")

        yield TurnCompleted(run.produced_messages)
