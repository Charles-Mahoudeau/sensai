"""Core pipeline abstractions: the Stage protocol, stage results, and Pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models import Message


@dataclass(frozen=True, slots=True)
class Continue:
    """Request go to the next stage."""

    messages: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class ShortCircuit:
    """The stage cut and give the response."""

    reply: Message


StageResult = Continue | ShortCircuit


class Stage(Protocol):
    """A single step of the pipeline that processes the messages."""

    def process(self, messages: tuple[Message, ...]) -> StageResult:
        """Process the messages and decide how the pipeline continues.

        Args:
            messages: The messages produced by the previous stage.

        Returns:
            ``Continue`` to pass messages to the next stage, or ``ShortCircuit``
            to stop the pipeline and return a reply directly.
        """
        ...


class Pipeline:
    """Run a sequence of stages in order, stopping on the first short-circuit."""

    def __init__(self, stages: Sequence[Stage] = ()) -> None:
        """Initialize the pipeline.

        Args:
            stages: The stages to run, in execution order.
        """
        self._stages = tuple(stages)

    def run(self, messages: Sequence[Message]) -> StageResult:
        """Run the messages through every stage.

        Args:
            messages: The initial messages fed to the first stage.

        Returns:
            The first ShortCircuit returned by a stage, or the final
            Continue if every stage let the messages through.
        """
        result: StageResult = Continue(tuple(messages))
        for stage in self._stages:
            result = stage.process(result.messages)
            if isinstance(result, ShortCircuit):
                return result
        return result
