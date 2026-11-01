"""Measure how generation settings change Sensai's answers to math questions.

Runs the ReAct agent on questions with a known answer, for every temperature
and seed asked, and prints Markdown tables: how often each temperature is
right, and how many different answers the seeds produced. `--recall` checks the
context length instead: a fact stated first, then enough text to push it past a
small context.

    uv run python scripts/sampling_experiment.py --model M --temperature 0 0.8 1.5
    uv run python scripts/sampling_experiment.py --model M --recall --num-ctx 2048 8192

Same model, settings, seed and Ollama version give the same tables.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from sensai.adapters.ollama import OllamaChat
from sensai.core.agent.events import TurnCompleted
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, ThinkingEffort
from sensai.core.models.llm import ChatOptions
from sensai.core.prompts.defaults import load_defaults
from sensai.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

OLLAMA_URL = "http://localhost:11434"


@dataclass(frozen=True)
class Question:
    """A math question and how to recognize a right answer."""

    name: str
    text: str
    is_right: Callable[[str], bool]


def _numbers(answer: str) -> str:
    """The answer with digit groups joined: `121 932 631` → `121932631`."""
    return re.sub(r"(?<=\d)[\s,](?=\d{3}\b)", "", answer)


def _has(*expected: str) -> Callable[[str], bool]:
    """Right when every expected piece appears, digit groups joined."""
    return lambda answer: all(piece in _numbers(answer) for piece in expected)


QUESTIONS = (
    Question(
        "product",
        "Combien font 123456789 fois 987654321 ? Donne le résultat exact.",
        _has("121932631112635269"),
    ),
    Question(
        "speed",
        "Un train parcourt 180 km en 2 h 30. Quelle est sa vitesse moyenne en km/h ?",
        _has("72"),
    ),
    Question(
        "derivative",
        "Soit f(x) = x^3 - 5x^2 + 2x. Calcule f'(2).",
        lambda answer: (
            re.search(r"(?<![\d.])[-\N{MINUS SIGN}]\s?6(?!\d|[.,]\d)", answer)
            is not None
        ),
    ),
    Question(
        "roots",
        "Quelles sont les racines de x^3 - 6x^2 + 11x - 6 ?",
        lambda answer: all(re.search(rf"\b{root}\b", answer) for root in "123"),
    ),
    Question(
        "limit",
        "Calcule la limite de (1 + 1/n)^(2n) quand n tend vers l'infini.",
        lambda answer: re.search(r"e\^\{?2|e²|7[.,]389", answer) is not None,
    ),
    Question(
        "dice",
        "On lance deux dés équilibrés. Quelle est la probabilité que la somme "
        "fasse 7 ?",
        lambda answer: (
            re.search(r"1\s?/\s?6|\\frac\{1\}\{6\}|0[.,]1667?", answer) is not None
        ),
    ),
)

RECALL_FACT = "Retiens ceci : ma constante de travail est k = 7.31."
RECALL_QUESTION = "Quelle est la valeur de ma constante de travail k ?"
FILLER = (
    "Voici un rappel de cours sans rapport. Une suite réelle (u_n) converge vers "
    "l si pour tout epsilon > 0 il existe un rang N tel que |u_n - l| < epsilon "
    "pour tout n >= N. Toute suite croissante et majorée converge. "
) * 12


def recall_is_right(answer: str) -> bool:
    """Right when the answer gives k = 7.31 (or 7,31)."""
    return re.search(r"7[.,]31", answer) is not None


def recall_messages() -> list[Message]:
    """The fact, then about 3,000 tokens of filler turns, then the question."""
    messages = [Message.user(RECALL_FACT), Message.assistant("C'est noté.")]
    for _ in range(4):
        messages += [Message.user(FILLER), Message.assistant("D'accord.")]
    return [*messages, Message.user(RECALL_QUESTION)]


async def ask(
    llm: OllamaChat, messages: Sequence[Message], options: ChatOptions
) -> str:
    """Run the agent once, without tools or thinking, and return its answer."""
    agent = ReActAgent(llm, ToolRegistry())
    agent.thinking_effort = ThinkingEffort.NONE
    agent.chat_options = options
    system = Message.system(load_defaults()["system"])
    answer = ""
    async for event in agent.run((system, *messages)):
        if isinstance(event, TurnCompleted) and event.messages:
            answer = event.messages[-1].content
    return answer


@dataclass(frozen=True)
class Result:
    """One answer to one question with one setting."""

    question: str
    setting: float
    answer: str
    right: bool
    seconds: float


def summary_table(results: Sequence[Result], setting: str) -> str:
    """Accuracy, distinct answers per question and time, for each setting."""
    lines = [
        f"| {setting} | right | distinct answers per question | time per answer |",
        "|---|---|---|---|",
    ]
    for value in dict.fromkeys(result.setting for result in results):
        group = [result for result in results if result.setting == value]
        right = sum(result.right for result in group)
        by_question: dict[str, set[str]] = {}
        for result in group:
            by_question.setdefault(result.question, set()).add(result.answer.strip())
        distinct = sum(map(len, by_question.values())) / len(by_question)
        seconds = sum(result.seconds for result in group) / len(group)
        lines.append(
            f"| {value:g} | {right}/{len(group)} ({right / len(group):.0%}) "
            f"| {distinct:.1f} | {seconds:.0f} s |"
        )
    return "\n".join(lines)


def question_table(results: Sequence[Result]) -> str:
    """Right answers per question (rows) and setting (columns)."""
    settings = list(dict.fromkeys(result.setting for result in results))
    lines = [
        "| question | " + " | ".join(f"{value:g}" for value in settings) + " |",
        "|---" * (len(settings) + 1) + "|",
    ]
    for question in dict.fromkeys(result.question for result in results):
        cells = []
        for value in settings:
            group = [
                result
                for result in results
                if result.question == question and result.setting == value
            ]
            cells.append(f"{sum(result.right for result in group)}/{len(group)}")
        lines.append(f"| {question} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def run_questions(args: argparse.Namespace, llm: OllamaChat) -> str:
    """Ask every question for each temperature and seed; return the tables."""
    results = []
    for temperature in args.temperature:
        for seed in args.seed:
            for question in QUESTIONS:
                options = ChatOptions(
                    temperature=temperature, seed=seed, num_ctx=args.num_ctx[0]
                )
                start = time.monotonic()
                answer = await ask(llm, [Message.user(question.text)], options)
                result = Result(
                    question.name,
                    temperature,
                    answer,
                    question.is_right(answer),
                    time.monotonic() - start,
                )
                print(
                    f"  T={temperature:g} seed={seed} {question.name}: "
                    f"{'right' if result.right else 'WRONG'}",
                    flush=True,
                )
                results.append(result)
    return f"{summary_table(results, 'temperature')}\n\n{question_table(results)}\n"


async def run_recall(args: argparse.Namespace, llm: OllamaChat) -> str:
    """Ask the recall question for each context length and seed."""
    results = []
    for num_ctx in args.num_ctx:
        for seed in args.seed:
            options = ChatOptions(
                temperature=args.temperature[0], seed=seed, num_ctx=num_ctx
            )
            start = time.monotonic()
            answer = await ask(llm, recall_messages(), options)
            result = Result(
                "recall",
                num_ctx,
                answer,
                recall_is_right(answer),
                time.monotonic() - start,
            )
            print(
                f"  num_ctx={num_ctx} seed={seed}: "
                f"{'right' if result.right else 'WRONG'}",
                flush=True,
            )
            results.append(result)
    return summary_table(results, "num_ctx") + "\n"


def build_parser() -> argparse.ArgumentParser:
    """The command-line options."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--temperature", type=float, nargs="+", default=[0.1])
    parser.add_argument("--seed", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--num-ctx", type=int, nargs="+", default=[8192])
    parser.add_argument(
        "--recall", action="store_true", help="test the context length instead"
    )
    parser.add_argument("--out", help="also write the tables to this file")
    return parser


async def main(args: argparse.Namespace) -> None:
    """Run the chosen experiment and print, or also save, its tables."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5)) as client:
        llm = OllamaChat(client, OLLAMA_URL, args.model, keep_alive="30m")
        run = run_recall if args.recall else run_questions
        tables = await run(args, llm)
    print(f"\n{tables}")
    if args.out:
        Path(args.out).write_text(tables, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main(build_parser().parse_args()))
