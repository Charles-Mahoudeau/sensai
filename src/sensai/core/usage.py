"""Count the tokens of every model call a session makes."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from sensai.core.models.llm import ChatDone, UsageReport, UsageTotals
from sensai.core.ports import LLMError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.model_memory import ModelMemory
    from sensai.core.models.llm import ChatEvent, ChatOptions, Message
    from sensai.core.models.tools import ToolSpec
    from sensai.core.ports import LLM


class UsageMeter:
    """Add up the usage of a session, and track what is not saved yet."""

    def __init__(self, start: UsageTotals | None = None) -> None:
        """Start from the totals already saved for the session.

        Args:
            start: The saved totals; zero for a new session.
        """
        self._total = start or UsageTotals()
        self._unsaved = UsageTotals()
        self._last: ChatDone | None = None

    @property
    def total(self) -> UsageTotals:
        """The usage of the whole session, saved or not."""
        return self._total

    @property
    def last(self) -> ChatDone | None:
        """The end of the latest model call, or None if there was none yet."""
        return self._last

    def record(self, done: ChatDone) -> None:
        """Count one more model call."""
        self._total = self._total.add(done)
        self._unsaved = self._unsaved.add(done)
        self._last = done

    def take_unsaved(self) -> UsageTotals:
        """Return the usage not saved yet, and stop tracking it as unsaved.

        If saving it then fails, hand it back with `restore_unsaved`.
        """
        unsaved = self._unsaved
        self._unsaved = UsageTotals()
        return unsaved

    def restore_unsaved(self, usage: UsageTotals) -> None:
        """Track usage taken by `take_unsaved` as unsaved again."""
        self._unsaved = usage + self._unsaved

    def reset(self, start: UsageTotals | None = None) -> None:
        """Start counting for another session.

        Args:
            start: The saved totals of that session; zero for a new one.
        """
        self._total = start or UsageTotals()
        self._unsaved = UsageTotals()
        self._last = None


class MeteredLLM:
    """Forward every call to a model, counting each one in a meter.

    Wrapping the model once means every caller is counted (each ReAct step,
    memory extraction, …) without any of them knowing about the meter.
    """

    def __init__(self, llm: LLM, meter: UsageMeter) -> None:
        """Store the model to forward to and the meter to count in.

        Args:
            llm: The model that answers.
            meter: Where each call's usage is added.
        """
        self._llm = llm
        self._meter = meter

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        options: ChatOptions | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Stream the model's answer unchanged, counting its final `ChatDone`."""
        async for event in self._llm.chat(messages, tools=tools, options=options):
            if isinstance(event, ChatDone):
                self._meter.record(event)
            yield event


async def usage_report(
    meter: UsageMeter | None, model_memory: ModelMemory | None
) -> UsageReport:
    """Gather the session usage, the context fill and the model's memory.

    A model server that cannot be reached only leaves the memory out: the
    report still has the token usage, and says why the memory is missing.

    The context fill comes from the latest model call, so it is unknown right
    after a restart, until the first message. That call may be the memory
    extraction rather than the answer; its prompt holds the conversation too.

    Args:
        meter: Counts the session's tokens; no usage if None.
        model_memory: Reads the model's memory footprint and context window;
            neither if None.
    """
    loaded_model = None
    context_max = None
    monitor_error = None
    if model_memory is not None:
        try:
            loaded_model = await model_memory.current()
        except LLMError as e:
            monitor_error = str(e)
        else:
            # Only asked when the server answered, so a down server costs one
            # timeout, not two. Without it the report just lacks the maximum.
            with contextlib.suppress(LLMError):
                context_max = await model_memory.max_context()
    last = meter.last if meter is not None else None
    return UsageReport(
        session=meter.total if meter is not None else UsageTotals(),
        loaded_model=loaded_model,
        context_used=last.usage.total_tokens if last is not None else None,
        context_max=context_max,
        monitor_error=monitor_error,
    )


if TYPE_CHECKING:

    def _conforms(wrapper: MeteredLLM) -> LLM:
        return wrapper
