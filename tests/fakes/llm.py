"""Scripted fake implementing the LLM port."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.core.models.llm import ChatDone

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.models.llm import ChatEvent, ChatOptions, Message
    from sensai.core.models.tools import ToolSpec
    from sensai.core.ports import LLM

type Turn = Sequence[ChatEvent | Exception]


class FakeLLM:
    """Plays back one scripted turn per `chat` call and records every request.

    A turn is a list of events to stream. An exception in the list is raised at
    that point, to simulate a failure mid-stream. A `ChatDone` is appended when
    the turn doesn't end with one, so tests only script what they care about.
    """

    def __init__(self, turns: Sequence[Turn]) -> None:
        """Store the scripted turns."""
        self._turns = iter(turns)
        self.messages: list[list[Message]] = []
        self.tools: list[list[ToolSpec]] = []
        self.options: list[ChatOptions | None] = []

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        options: ChatOptions | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Record the request, then stream the next scripted turn."""
        self.messages.append(list(messages))
        self.tools.append(list(tools))
        self.options.append(options)
        turn = next(self._turns)
        for item in turn:
            if isinstance(item, Exception):
                raise item
            yield item
        if not turn or not isinstance(turn[-1], ChatDone):
            yield ChatDone()


if TYPE_CHECKING:

    def _conforms(fake: FakeLLM) -> LLM:
        return fake
