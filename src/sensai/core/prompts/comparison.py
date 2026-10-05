"""Compare two versions of a prompt on the same inputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import fmean
from typing import TYPE_CHECKING, Literal

from sensai.core.models import ChatDone, Message, TextDelta
from sensai.core.models.llm import ChatOptions

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sensai.core.models.prompts import PromptVersion
    from sensai.core.ports import LLM

type Winner = Literal["A", "B", "tie"]

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "tie"]},
        "reason": {"type": "string"},
    },
    "required": ["winner", "reason"],
}
_JUDGE_OPTIONS = ChatOptions(temperature=0.0, response_schema=_JUDGE_SCHEMA)
_SWAPPED: dict[str, Winner] = {"A": "B", "B": "A", "tie": "tie"}


@dataclass(frozen=True, slots=True)
class Answer:
    """One version's answer to one input."""

    text: str
    latency: float
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True, slots=True)
class InputResult:
    """Both answers to one input, and the judge's verdict if it ran."""

    input: str
    a: Answer
    b: Answer
    winner: Winner | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VersionSummary:
    """Averages and wins of one version over every input."""

    version: int
    mean_latency: float
    mean_completion_tokens: float
    mean_length: float
    wins: int


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """The outcome of a comparison run."""

    name: str
    a: VersionSummary
    b: VersionSummary
    ties: int
    judged: bool
    results: tuple[InputResult, ...]


class PromptComparison:
    """Runs two versions of a prompt, used as the system message, on the same inputs.

    For each input, both answers are measured (latency, tokens, length). When a
    judge prompt is given, the model also judges which answer is better. It is
    asked twice with the answers swapped, and a disagreement counts as a tie, so
    the order the answers are shown in doesn't decide the result.
    """

    def __init__(self, llm: LLM, clock: Callable[[], float]) -> None:
        """Use `llm` for answers and verdicts; `clock` returns seconds."""
        self._llm = llm
        self._clock = clock

    async def compare(
        self,
        a: PromptVersion,
        b: PromptVersion,
        inputs: Sequence[str],
        *,
        judge_prompt: str | None = None,
    ) -> ComparisonReport:
        """Answer every input with both versions and summarize the results.

        Raises:
            ValueError: `inputs` is empty.
            LLMError: The model failed.
        """
        if not inputs:
            raise ValueError("a comparison needs at least one input")
        results: list[InputResult] = []
        for text in inputs:
            answer_a = await self._answer(a.content, text)
            answer_b = await self._answer(b.content, text)
            result = InputResult(text, answer_a, answer_b)
            if judge_prompt is not None:
                result = await self._judge(judge_prompt, result)
            results.append(result)
        return ComparisonReport(
            name=a.name,
            a=_summarize(a.version, [r.a for r in results], results, "A"),
            b=_summarize(b.version, [r.b for r in results], results, "B"),
            ties=sum(r.winner == "tie" for r in results),
            judged=judge_prompt is not None,
            results=tuple(results),
        )

    async def _answer(self, system: str, text: str) -> Answer:
        start = self._clock()
        reply, done = await self._chat([Message.system(system), Message.user(text)])
        usage = done.usage
        return Answer(
            reply, self._clock() - start, usage.prompt_tokens, usage.completion_tokens
        )

    async def _judge(self, prompt: str, result: InputResult) -> InputResult:
        first, first_reason = await self._verdict(
            prompt, result.input, result.a, result.b
        )
        second, second_reason = await self._verdict(
            prompt, result.input, result.b, result.a
        )
        winner = first if first == _SWAPPED[second] else "tie"
        return InputResult(
            result.input, result.a, result.b, winner, (first_reason, second_reason)
        )

    async def _verdict(
        self, prompt: str, request: str, first: Answer, second: Answer
    ) -> tuple[Winner, str]:
        question = (
            f"User request:\n{request}\n\n"
            f"Answer A:\n{first.text}\n\n"
            f"Answer B:\n{second.text}"
        )
        reply, _ = await self._chat(
            [Message.system(prompt), Message.user(question)], _JUDGE_OPTIONS
        )
        return _parse_verdict(reply)

    async def _chat(
        self, messages: list[Message], options: ChatOptions | None = None
    ) -> tuple[str, ChatDone]:
        parts: list[str] = []
        done = ChatDone()
        async for event in self._llm.chat(messages, options=options):
            match event:
                case TextDelta(text):
                    parts.append(text)
                case ChatDone():
                    done = event
        return "".join(parts), done


def _parse_verdict(reply: str) -> tuple[Winner, str]:
    """Read the judge's JSON; an unreadable verdict counts as a tie."""
    try:
        data = json.loads(reply)
        winner = data["winner"]
        reason = str(data.get("reason", ""))
    except json.JSONDecodeError, KeyError, TypeError:
        return "tie", f"unreadable verdict: {reply[:80]!r}"
    if winner not in _SWAPPED:
        return "tie", f"unknown winner: {winner!r}"
    return winner, reason


def _summarize(
    version: int,
    answers: list[Answer],
    results: list[InputResult],
    side: Winner,
) -> VersionSummary:
    return VersionSummary(
        version=version,
        mean_latency=fmean(a.latency for a in answers),
        mean_completion_tokens=fmean(a.completion_tokens for a in answers),
        mean_length=fmean(len(a.text) for a in answers),
        wins=sum(r.winner == side for r in results),
    )
