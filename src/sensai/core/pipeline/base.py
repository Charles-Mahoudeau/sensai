"""Core pipeline abstractions: the Stage protocol, stage results, and Pipeline."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Continue:
    """Request go to the next stage."""
    messages: tuple[str, ...]

@dataclass(frozen=True)
class ShortCircuit:
    """The stage cut and give the response."""
    reply: str


StageResult = Continue | ShortCircuit

class Stage(Protocol):
    def process(self, messages: tuple[str, ...]) -> StageResult:
        ...


class Pipeline:
    def __init__(self, stages: Sequence[Stage] = ()) -> None:
        self._stages = tuple(stages)

    def run(self, messages: Sequence[str]) -> StageResult:
        result: StageResult = Continue(tuple(messages))
        for stage in self._stages:
            result = stage.process(result.messages)
            if isinstance(result, ShortCircuit):
                return result
        return result