"""Benchmark Ollama models on Sensai's use case: speed, memory and answer quality.

Every model answers the same questions (`benchmarks/cases.toml`) with the same
system prompt and generation settings (`config/benchmark.toml`). The results are
saved as JSON and as a Markdown report under `benchmarks/results/`:

    uv run python scripts/benchmark.py [--config FILE] [--models M ...] [--cases ID ...]
    uv run python scripts/benchmark.py --rescore benchmarks/results/<run>

Every call goes to the Ollama HTTP API through Sensai's own adapters.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import re
import sys
import time
import tomllib
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from sensai.adapters.ollama import OllamaChat, OllamaMonitor
from sensai.core.models.llm import ChatDone, ChatOptions, Message, TextDelta
from sensai.core.ports import LLMError

_GIB = 1024**3
_MISSING = "-"
_FINAL_LINE = re.compile(r"^r[ée]ponse\s+finale\s*:\s*(.*)$", re.IGNORECASE)
_MARKDOWN = "*_#>` "
_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
}
_JUDGE_PROMPT = """\
Tu évalues la réponse d'un tuteur de mathématiques à un élève de Terminale en
difficulté. Note de 1 à 5 à quel point la réponse l'aide à comprendre la méthode :
5 = méthode expliquée, chaque étape justifiée et calculs justes, en français ;
3 = résultat juste mais étapes sautées ou peu expliquées ;
1 = faux, hors sujet, ou pas en français.

Question :
{question}

Réponse du tuteur :
{answer}
"""


@dataclass(frozen=True)
class Case:
    """One benchmark question, and how to check its answer."""

    id: str
    category: str
    topic: str
    prompt: str
    must_match: tuple[str, ...] = ()
    must_not_match: tuple[str, ...] = ()


@dataclass(frozen=True)
class Settings:
    """What `config/benchmark.toml` sets."""

    machine: str
    description: str
    url: str
    cases: Path
    results_dir: Path
    models: tuple[str, ...]
    generation: dict[str, Any]
    system_prompt: str
    judge_model: str | None


@dataclass
class CaseResult:
    """One model's answer to one question, with its measurements."""

    case_id: str
    answer: str = ""
    final_line: str | None = None
    correct: bool | None = None
    first_token_s: float | None = None
    total_s: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    generation_tok_s: float | None = None
    prompt_tok_s: float | None = None
    truncated: bool = False
    judge_score: int | None = None
    judge_reason: str | None = None
    error: str | None = None


@dataclass
class ModelResult:
    """Everything measured for one model."""

    model: str
    parameters: str | None = None
    quantization: str | None = None
    load_s: float | None = None
    memory_bytes: int | None = None
    vram_bytes: int | None = None
    context_length: int | None = None
    cases: list[CaseResult] = field(default_factory=list)
    error: str | None = None


def load_settings(path: Path) -> Settings:
    """Read the benchmark settings; paths in them are relative to the repository."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent.parent
    run = data["run"]
    judge = data.get("judge", {})
    return Settings(
        machine=data["machine"]["name"],
        description=data["machine"].get("description", ""),
        url=data["ollama"]["url"],
        cases=root / run["cases"],
        results_dir=root / run["results_dir"],
        models=tuple(run["models"]),
        generation=data.get("generation", {}),
        system_prompt=data["prompt"]["system"].strip(),
        judge_model=judge.get("model") if judge.get("enabled") else None,
    )


def load_cases(path: Path) -> list[Case]:
    """Read the benchmark questions."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [
        Case(
            id=raw["id"],
            category=raw["category"],
            topic=raw["topic"],
            prompt=raw["prompt"].strip(),
            must_match=tuple(raw.get("must_match", ())),
            must_not_match=tuple(raw.get("must_not_match", ())),
        )
        for raw in data["cases"]
    ]


def normalize(text: str) -> str:
    """Make an answer comparable with the regexes of `cases.toml`."""
    text = text.lower().replace("\u2212", "-").replace("ˣ", "^x")
    text = text.replace("^2", "²").replace("^3", "³")
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    return re.sub(r"[\s*·$\\]", "", text)


def final_line(answer: str) -> str | None:
    """Return what follows the last "Réponse finale :", or None if it is missing."""
    lines = [line.strip().strip(_MARKDOWN) for line in answer.splitlines()]
    for index in range(len(lines) - 1, -1, -1):
        if match := _FINAL_LINE.match(lines[index]):
            rest = match.group(1).strip(_MARKDOWN)
            following = [line for line in lines[index + 1 :] if line]
            return rest or (following[0] if following else "")
    return None


def is_correct(case: Case, answer: str, final: str | None) -> bool | None:
    """Check an answer against its case; None when the case has nothing to check.

    Without a final line, the last three non-empty lines are checked instead, so
    a correct answer in the wrong format still counts as correct.
    """
    if not case.must_match:
        return None
    if final is None:
        final = " ".join([line for line in answer.splitlines() if line.strip()][-3:])
    text = normalize(final)
    return all(re.search(p, text) for p in case.must_match) and not any(
        re.search(p, text) for p in case.must_not_match
    )


def _with_tag(name: str) -> str:
    """Add the tag Ollama assumes when none is given (`qwen3` → `qwen3:latest`)."""
    return name if ":" in name else f"{name}:latest"


def _options(settings: Settings, **overrides: Any) -> ChatOptions:
    generation = settings.generation | overrides
    return ChatOptions(
        temperature=generation.get("temperature"),
        top_p=generation.get("top_p"),
        seed=generation.get("seed"),
        num_ctx=generation.get("num_ctx"),
        max_tokens=generation.get("num_predict"),
        response_schema=generation.get("response_schema"),
    )


async def _answer(
    llm: OllamaChat, messages: list[Message], options: ChatOptions
) -> tuple[str, ChatDone, float | None, float]:
    """Stream one answer; return its text, final event, first-token and total time."""
    start = time.perf_counter()
    first_token: float | None = None
    parts: list[str] = []
    async for event in llm.chat(messages, options=options):
        if isinstance(event, TextDelta):
            if first_token is None:
                first_token = time.perf_counter() - start
            parts.append(event.text)
        elif isinstance(event, ChatDone):
            return "".join(parts), event, first_token, time.perf_counter() - start
    raise LLMError("the answer ended without a final event")


async def _details(client: httpx.AsyncClient, url: str, model: str) -> dict[str, Any]:
    """Read a model's size and quantization from `/api/show`."""
    response = await client.post(f"{url}/api/show", json={"model": model})
    response.raise_for_status()
    return response.json().get("details", {})


async def _unload(client: httpx.AsyncClient, url: str, model: str) -> None:
    """Free the model's memory, so the next model is measured alone."""
    await OllamaChat(client, url, model, keep_alive=0).load()


async def run_model(
    client: httpx.AsyncClient, settings: Settings, model: str, cases: list[Case]
) -> ModelResult:
    """Load one model, measure its footprint, then ask it every question."""
    result = ModelResult(model)
    llm = OllamaChat(client, settings.url, model, keep_alive="10m")
    monitor = OllamaMonitor(client, settings.url)
    options = _options(settings)
    try:
        details = await _details(client, settings.url, model)
        result.parameters = details.get("parameter_size")
        result.quantization = details.get("quantization_level")
        # A first short answer loads the model with the benchmark's context
        # window, which sets its memory; the load time is the cold start.
        warmup = _options(settings, num_predict=1)
        _, done, _, _ = await _answer(llm, [Message.user("Bonjour")], warmup)
        result.load_s = done.timings.load.total_seconds() if done.timings else None
        for loaded in await monitor.loaded_models():
            if _with_tag(loaded.name) == _with_tag(model):
                result.memory_bytes = loaded.size_bytes
                result.vram_bytes = loaded.vram_bytes
                result.context_length = loaded.context_length
    except (LLMError, httpx.HTTPError) as error:
        result.error = str(error) or type(error).__name__
        print(f"  {model}: {result.error}", flush=True)
        return result

    system = Message.system(settings.system_prompt)
    for number, case in enumerate(cases, start=1):
        print(f"  [{number}/{len(cases)}] {case.id} … ", end="", flush=True)
        outcome = CaseResult(case.id)
        try:
            text, done, first, total = await _answer(
                llm, [system, Message.user(case.prompt)], options
            )
        except LLMError as error:
            outcome.error = str(error) or type(error).__name__
            print(f"error: {outcome.error}", flush=True)
        else:
            outcome.answer = text
            outcome.final_line = final_line(text)
            outcome.correct = is_correct(case, text, outcome.final_line)
            outcome.first_token_s = first
            outcome.total_s = total
            outcome.prompt_tokens = done.usage.prompt_tokens
            outcome.completion_tokens = done.usage.completion_tokens
            outcome.generation_tok_s = done.completion_tokens_per_second
            outcome.prompt_tok_s = done.prompt_tokens_per_second
            outcome.truncated = done.done_reason == "length"
            mark = {True: "correct", False: "wrong", None: "no check"}[outcome.correct]
            print(f"{mark}, {total:.0f} s", flush=True)
        result.cases.append(outcome)
    await _unload(client, settings.url, model)
    return result


async def judge(
    client: httpx.AsyncClient,
    settings: Settings,
    model: str,
    results: list[ModelResult],
    cases: list[Case],
) -> None:
    """Grade how well each answer explains the method, from 1 to 5."""
    llm = OllamaChat(client, settings.url, model, keep_alive="10m")
    options = _options(settings, num_predict=256, response_schema=_JUDGE_SCHEMA)
    prompts = {case.id: case.prompt for case in cases}
    for result in results:
        for outcome in result.cases:
            if outcome.error is not None or not outcome.answer:
                continue
            prompt = _JUDGE_PROMPT.format(
                question=prompts[outcome.case_id], answer=outcome.answer
            )
            try:
                text, _, _, _ = await _answer(llm, [Message.user(prompt)], options)
                verdict = json.loads(text)
                outcome.judge_score = int(verdict["score"])
                outcome.judge_reason = str(verdict["reason"])
            except (LLMError, ValueError, KeyError, TypeError) as error:
                outcome.judge_reason = f"judge failed: {error}"
            print(
                f"  {result.model} / {outcome.case_id}: {outcome.judge_score}",
                flush=True,
            )
    await _unload(client, settings.url, model)


def machine_info() -> dict[str, str]:
    """Describe the CPU and memory of the machine running the benchmark."""
    info = {"system": f"{platform.system()} {platform.release()}"}
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal"):
                kib = int(line.split()[1])
                info["ram"] = f"{kib * 1024 / _GIB:.1f} GiB"
                break
    info.setdefault("cpu", platform.processor() or "unknown")
    return info


def _mean(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None


def _fmt(value: float | None, digits: int = 1) -> str:
    return _MISSING if value is None else f"{value:.{digits}f}"


def _score(outcomes: list[CaseResult]) -> str:
    checked = [o for o in outcomes if o.correct is not None]
    if not checked:
        return _MISSING
    return f"{sum(o.correct is True for o in checked)}/{len(checked)}"


def report(
    settings: Settings,
    meta: dict[str, Any],
    results: list[ModelResult],
    cases: list[Case],
) -> str:
    """Write the results as Markdown tables, one model per row."""
    generation = ", ".join(f"{k}={v}" for k, v in settings.generation.items())
    lines = [
        f"# Benchmark · {settings.machine} · {meta['started']}",
        "",
        f"- Machine: {settings.description}",
        f"- CPU: {meta['machine']['cpu']} · RAM: {meta['machine'].get('ram', '?')} · "
        f"{meta['machine']['system']}",
        f"- Ollama {meta['ollama_version']}",
        f"- Generation: {generation}",
        f"- Questions: {len(cases)} ({sum(c.category == 'use_case' for c in cases)} "
        "from the use case)",
        "",
        "## Speed and memory",
        "",
        "| Model | Size | Quant. | Load (s) | First token (s) | Generation (tok/s) "
        "| Prompt (tok/s) | Answer time (s) | Memory (GiB) | Of which VRAM (GiB) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.error is not None:
            lines.append(f"| {r.model} | | | error: {r.error} | | | | | | |")
            continue
        ok = [o for o in r.cases if o.error is None]
        lines.append(
            f"| {r.model} | {r.parameters or '?'} | {r.quantization or '?'} "
            f"| {_fmt(r.load_s)} | {_fmt(_mean([o.first_token_s for o in ok]))} "
            f"| {_fmt(_mean([o.generation_tok_s for o in ok]))} "
            f"| {_fmt(_mean([o.prompt_tok_s for o in ok]))} "
            f"| {_fmt(_mean([o.total_s for o in ok]))} "
            f"| {_fmt(r.memory_bytes / _GIB if r.memory_bytes else None, 2)} "
            f"| {_fmt(r.vram_bytes / _GIB if r.vram_bytes is not None else None, 2)} |"
        )
    lines += [
        "",
        "## Answer quality",
        "",
        "| Model | Use case correct | Generic correct | Final line given "
        "| Truncated | Errors | Judge (1-5) |",
        "|---|---|---|---|---|---|---|",
    ]
    category = {case.id: case.category for case in cases}
    for r in results:
        if r.error is not None:
            continue
        answered = [o for o in r.cases if o.error is None]
        use_case = [o for o in r.cases if category[o.case_id] == "use_case"]
        generic = [o for o in r.cases if category[o.case_id] == "generic"]
        judged = [float(o.judge_score) for o in r.cases if o.judge_score is not None]
        lines.append(
            f"| {r.model} | {_score(use_case)} | {_score(generic)} "
            f"| {sum(o.final_line is not None for o in answered)}/{len(answered)} "
            f"| {sum(o.truncated for o in answered)} "
            f"| {len(r.cases) - len(answered)} | {_fmt(_mean(list(judged)), 2)} |"
        )
    shown = [r for r in results if r.error is None]
    lines += [
        "",
        "## Per question",
        "",
        "✓ correct · ✗ wrong · - nothing to check (judge only) · ! error · "
        "(t) truncated",
        "",
        "| Question | Topic | " + " | ".join(r.model for r in shown) + " |",
        "|---|---|" + "---|" * len(shown),
    ]
    for case in cases:
        cells = []
        for r in shown:
            outcome = next((o for o in r.cases if o.case_id == case.id), None)
            if outcome is None or outcome.error is not None:
                cells.append("!")
                continue
            cell = {True: "✓", False: "✗", None: _MISSING}[outcome.correct]
            cell += " (t)" if outcome.truncated else ""
            if outcome.judge_score is not None:
                cell += f" · {outcome.judge_score}/5"
            cells.append(cell)
        lines.append(f"| {case.id} | {case.topic} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Every answer, final line and judge reason is in `results.json`.",
        "",
    ]
    return "\n".join(lines)


async def run(settings: Settings, models: tuple[str, ...], cases: list[Case]) -> Path:
    """Benchmark every model, then save the results; return their folder."""
    started = datetime.now()
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0)) as client:
        try:
            version = (await client.get(f"{settings.url}/api/version")).json()
        except httpx.HTTPError as error:
            sys.exit(f"cannot reach Ollama at {settings.url}: {error}")
        results = []
        for model in models:
            print(f"{model}", flush=True)
            results.append(await run_model(client, settings, model, cases))
        if settings.judge_model is not None:
            print(f"judge: {settings.judge_model}", flush=True)
            await judge(client, settings, settings.judge_model, results, cases)

    meta = {
        "started": started.strftime("%Y-%m-%d %H:%M"),
        "machine": machine_info(),
        "ollama_version": version.get("version", "?"),
        "judge_model": settings.judge_model,
    }
    folder = settings.results_dir / f"{started:%Y-%m-%d_%H%M}-{settings.machine}"
    save(folder, settings, meta, results, cases)
    return folder


def save(
    folder: Path,
    settings: Settings,
    meta: dict[str, Any],
    results: list[ModelResult],
    cases: list[Case],
) -> None:
    """Write `results.json` and `report.md` into `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": meta,
        "settings": {
            "machine": settings.machine,
            "description": settings.description,
            "generation": settings.generation,
            "system_prompt": settings.system_prompt,
        },
        "cases": [asdict(case) for case in cases],
        "results": [asdict(result) for result in results],
    }
    (folder / "results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "report.md").write_text(
        report(settings, meta, results, cases), encoding="utf-8"
    )


def rescore(folder: Path, settings: Settings) -> None:
    """Check saved answers again with the current `cases.toml`, without any model.

    Only the checks change: the answers, timings and memory stay as measured.
    """
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    current = {case.id: case for case in load_cases(settings.cases)}
    cases = [current.get(raw["id"]) or Case(**raw) for raw in data["cases"]]
    by_id = {case.id: case for case in cases}
    results = []
    for raw in data["results"]:
        outcomes = [CaseResult(**outcome) for outcome in raw.pop("cases")]
        for outcome in outcomes:
            if outcome.error is None:
                outcome.final_line = final_line(outcome.answer)
                outcome.correct = is_correct(
                    by_id[outcome.case_id], outcome.answer, outcome.final_line
                )
        results.append(ModelResult(**raw, cases=outcomes))
    saved = data["settings"]
    settings = replace(
        settings,
        machine=saved["machine"],
        description=saved["description"],
        generation=saved["generation"],
        system_prompt=saved["system_prompt"],
    )
    save(folder, settings, data["meta"], results, cases)


def main() -> None:
    """Parse the command line and run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config", type=Path, default=Path("config/benchmark.toml"), help="settings"
    )
    parser.add_argument("--models", nargs="+", help="only these models")
    parser.add_argument("--cases", nargs="+", help="only these question ids")
    parser.add_argument(
        "--rescore",
        type=Path,
        metavar="FOLDER",
        help="check the answers saved in FOLDER again with the current cases.toml",
    )
    args = parser.parse_args()

    settings = load_settings(args.config)
    if args.rescore is not None:
        rescore(args.rescore, settings)
        print(f"Report: {args.rescore / 'report.md'}")
        return
    cases = load_cases(settings.cases)
    if args.cases:
        unknown = set(args.cases) - {case.id for case in cases}
        if unknown:
            sys.exit(f"unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case.id in args.cases]
    models = tuple(args.models or settings.models)

    folder = asyncio.run(run(settings, models, cases))
    print(f"\nReport: {folder / 'report.md'}")


if __name__ == "__main__":
    main()
