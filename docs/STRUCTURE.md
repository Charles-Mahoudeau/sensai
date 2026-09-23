# Source Structure Convention

This document explains **where code goes** in Sensai and **why**. Read it before adding a module, and link to it in
review comments when something is in the wrong place.

> **About the examples.** File names, module names, class names, method signatures and code snippets in this document
> (`OllamaChat`, `RagInjector`, `core/ports/retrieval.py`, `FakeLLM`, `Engine.submit()`…) are **examples** chosen to
> illustrate the conventions. They are not a spec, and the actual code doesn't need to match them. Name and shape things
> however the implementation requires.
>
> What *is* binding are the **rules**: the zones (`core/`, `adapters/`, `app.py`), the direction of dependencies, when
> to create a port, where shared vs owned models go, the `__init__.py` rules, and the PR checklist. When the real code
> diverges from an example, follow the rule, not the example. Remember to keep the import-linter module lists in
> `pyproject.toml` in sync with the packages that actually exist.

## TL;DR — the five rules

1. **All importable code lives in `src/sensai/`.** Nothing importable sits at the repo root.
2. **`core/` never imports `adapters/`, `cli.py` or `app.py`**, and never imports an infrastructure library (`httpx`,
   `fastapi`, the TUI library…). CI enforces this.
3. **`core/` holds the logic; adapters only translate.** When the core needs something from the outside world, it
   declares a port (a `typing.Protocol` in `core/ports/`) and an adapter implements it.
   See [Ports, explained](#ports-explained).
4. **Everything is wired together in exactly one place: `app.py`.** No module builds its own dependencies.
5. **Front-ends only use the engine facade and the event stream.** They never reach into the agent loop, the pipeline or
   the tool registry.

## The tree

Every directory under `src/sensai/` and `tests/` contains an `__init__.py`. They're left out below for readability;
see [Packages and `__init__.py`](#packages-and-__init__py).

The top-level zones are fixed; the files inside them are illustrative and will differ in the real codebase.

```
sensai/
├── pyproject.toml            # deps, extras, entry points, tool config
├── uv.lock                   # committed; never edited by hand
├── .python-version
├── README.md
├── config/
│   ├── sensai.toml           # default model, feature toggles
│   └── personas/             # one .toml per persona
├── docs/
│   ├── STRUCTURE.md          # this file
│   └── user-stories/         # one .md per feature
├── src/sensai/
│   ├── __main__.py           # `python -m sensai` → calls cli.main()
│   ├── cli.py                # argument parsing only, then hands off to app.py
│   ├── app.py                # composition root: builds adapters, injects them into core
│   ├── config.py             # loads and validates config (no business logic)
│   │
│   ├── core/                 # THE PRODUCT. Pure Python, no infrastructure imports.
│   │   ├── ports/            # interfaces the core needs from outside, one module per concern
│   │   │   ├── llm.py        # LLM + its errors
│   │   │   ├── retrieval.py  # Embedder, VectorStore
│   │   │   └── memory.py     # MemoryStore, SessionStore
│   │   ├── models/           # SHARED data types only, one module per concern
│   │   │   ├── chat.py       # Message, ToolCall, TextDelta, ToolCallRequest, ChatEvent
│   │   │   ├── tools.py      # ToolSpec, ToolResult
│   │   │   └── retrieval.py  # Chunk, ScoredChunk
│   │   ├── engine.py         # public facade used by front-ends
│   │   ├── events/           # event types + async bus
│   │   ├── pipeline/         # stage protocol + one module per stage
│   │   │   ├── base.py
│   │   │   ├── cache.py
│   │   │   ├── guard.py
│   │   │   └── rag.py
│   │   ├── agent/            # execution loop, ReAct mode, plan mode state machine
│   │   └── tools/            # registry, permission layer, built-in tools
│   │       ├── registry.py
│   │       ├── permissions.py
│   │       └── builtin/      # list_dir, read_file, ask_user_question…
│   │
│   └── adapters/             # THE PLUMBING. Implements ports, wraps libraries.
│       ├── ollama/           # chat + embeddings over the Ollama HTTP API
│       ├── vectorstore/
│       ├── memory/           # sqlite session + structured memory
│       ├── mcp/              # MCP client(s), exposed as registry tools
│       ├── sandbox/          # sandboxed code execution
│       ├── tui/              # terminal front-end
│       └── api/              # FastAPI front-end
└── tests/
    ├── fakes/                # FakeLLM, InMemoryVectorStore… (implement the ports)
    ├── core/                 # mirrors src/sensai/core/
    └── adapters/             # mirrors src/sensai/adapters/
```

## The three zones

### `core/` — what Sensai *is*

Everything that makes Sensai behave the way it does: the request pipeline, the agent loop (including ReAct and plan
mode), tool dispatch, permissions, the event bus. If you can describe it without naming a library or a protocol ("the
guardrail stage rejects a prompt when the model doesn't call `send_result`"), it belongs here.

**The core is where almost all of our code lives.** The `ports/` folder is a small part of it, just signatures.
Everything else in `core/` is real logic.

Core code depends only on the standard library and on other `core/` modules (including `core/ports/`). It receives its
dependencies through constructors:

```python
# core/pipeline/rag.py
class RagInjector:
    def __init__(self, embedder: Embedder, store: VectorStore, k: int = 5) -> None:
        ...
```

It never does `from sensai.adapters.ollama import OllamaClient`.

### `adapters/` — how Sensai *connects*

Each adapter implements one or more ports, or drives the core from the outside (front-ends). Adapters are where HTTP
calls, SQL, wire formats, FastAPI routes and terminal rendering live. **Adapters translate; they don't decide.** If an
adapter starts choosing which chunks to keep or retrying with a reworded prompt, that logic has leaked out of the core
and must move back.

Adapters may import `core/` (to implement its ports and use its models). Adapters **do not import each other**: if the
TUI needs something the API also needs, it belongs in `core/`.

### `app.py` — where they meet

The composition root. It reads config, instantiates adapters, builds the pipeline and the agent, and returns an
`Engine`. It is the only module allowed to know about every concrete class. Keep it boring: construction and wiring
only, no logic.

```python
# app.py
def build_engine(cfg: Config) -> Engine:
    http = httpx.AsyncClient(timeout=None)
    llm = OllamaChat(http, cfg.ollama_url, cfg.model)
    embedder = OllamaEmbedder(http, cfg.ollama_url, cfg.embed_model)
    store = SqliteVectorStore(cfg.data_dir / "vectors.db")

    registry = ToolRegistry(permissions=Permissions.from_config(cfg))
    register_builtins(registry)
    for server in cfg.mcp_servers:
        register_mcp_server(registry, server)

    stages = [RagInjector(embedder, store)]
    if cfg.guardrails.enabled:
        stages.insert(0, PromptGuard(llm))
    if cfg.cache.enabled:
        stages.insert(0, SemanticCache(embedder, threshold=cfg.cache.threshold))

    return Engine(pipeline=Pipeline(stages), agent=Agent(llm, registry), bus=EventBus())
```

Togglable features are toggled **here**, by including or leaving out a stage, not with `if` flags scattered through the
core.

## Ports, explained

This is the part of the structure people most often get wrong, so it gets its own section.

### The mental model

Three things work together:

|                            | What it is                                                                                                            | Size                            |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------|---------------------------------|
| **Core**                   | All the logic that makes Sensai behave the way it does                                                                | Most of the codebase            |
| **Ports** (`core/ports/`)  | The interfaces the core *needs from the outside world*: "something that can chat", "something that can store vectors" | A few dozen lines of signatures |
| **Adapters** (`adapters/`) | Implementations of those interfaces that *transport* data: HTTP to Ollama, SQL to SQLite                              | Thin                            |

The principle is **fat core, thin adapters**.

A common misreading is "ports are the interfaces, adapters are the implementations, so the core is basically empty".
It's the opposite. Ports describe only the core's *dependencies on the outside*. The core's own logic (pipeline stages,
agent loop, registry, permissions) is implemented in the core, and it *uses* those ports.

### The swap test

To decide whether something belongs in the core or in an adapter, ask: **if we replaced Ollama with another model
server (llama.cpp, vLLM), what would we have to rewrite?**

- Only `adapters/ollama/` should change.
- The guardrail logic, RAG strategy, ReAct loop, plan mode and permissions stay the same, because none of them are
  *about* Ollama. They're all core.

The same test works for any adapter: swap SQLite for another store and only `adapters/memory/` changes.

### Example: ReAct lives entirely in the core

`core/agent/` contains the whole reasoning strategy:

- the reasoning prompt,
- the reason → act → observe loop,
- reading the model's tool calls and feeding tool results back,
- stopping when the model calls `send_result`,
- the max-iterations guard against infinite loops.

When the loop needs the model, it calls `self._llm.chat(...)` through the `LLM` port. When it needs a tool, it goes
through the registry. The loop has no idea Ollama exists.

To test it, we don't mock the loop. We give it a `FakeLLM` that scripts the model's behavior ("call `read_file`", then
"call `send_result`") and check that the loop reacts correctly at each step.

### When does something get a port?

A dependency gets a port when it's **outside the process or outside our control** and at least one of these is true:

- **Tests need a fake:** it's slow, non-deterministic or unavailable in CI. The LLM and the embedder are the obvious
  cases, and this is the strongest reason.
- **We might swap it:** the vector store and the memory backend.
- **Its library types would leak into the core:** `httpx.Response`, `sqlite3.Row`, raw Ollama JSON or the MCP SDK's
  objects must never appear in core signatures.

**Not everything outside gets a port.** Some dependencies are simple enough to use directly from the core via the
standard library:

- **Filesystem for built-in tools.** `read_file` and `list_dir` use `pathlib` directly in `core/tools/builtin/`. Tests
  use pytest's `tmp_path`, which gives a real temporary directory, so there's nothing to fake and nothing to swap.
- **Time.** If something needs "now", take a `clock: Callable[[], datetime]` in the constructor. Tests pass
  `lambda: datetime(2026, 1, 1)`. A whole Protocol would be overkill.

**Rule of thumb: logic goes in the core. A dependency gets a port if tests need a fake or we might swap it. Otherwise,
use the standard library directly or pass a simple callable.**

### How a port works in Python

A port is a `typing.Protocol`: an interface checked by **shape**, not by inheritance. A class satisfies `LLM` if it has
a `chat` method with a matching signature, whether or not it inherits from `LLM` or even imports it (structural typing,
a.k.a. static duck typing).

- **At runtime a Protocol does nothing.** It's an annotation with zero cost and zero checks. The **type checker** in CI
  is what verifies that `OllamaChat` fits `LLM`, at every place an `OllamaChat` is passed where an `LLM` is expected.
- **Don't use `@runtime_checkable` for validation.** It only checks that method *names* exist, not their signatures.
- **Adapters don't need to inherit from the port.** Our convention: don't inherit.

#### How the type check actually works

The checker never looks at class declarations to decide whether `OllamaChat` "is an" `LLM`. It checks **wherever a value
flows into something typed as the port**: a function argument, an assignment, a return value.

```python
agent = Agent(llm=OllamaChat(http, url, model))  # Agent.__init__(self, llm: LLM, ...)
```

On that line it compares `OllamaChat` to `LLM` member by member:

1. **Every member of the port must exist** on the adapter.
2. **Parameters:** the adapter must accept *at least* what the port promises callers can pass. Port says
   `Sequence[Message]`, adapter says `list[Message]` → error, because the core may pass a tuple.
3. **Return type:** the adapter may return something *more specific*. An `async def` with `yield` returns an
   `AsyncGenerator`, a subtype of `AsyncIterator`, so it matches.
4. **Parameter names count**, since callers may pass them as keywords.

A mismatch is reported on that line, listing the expected and actual signatures. The same check runs in tests wherever a
fake is passed in, so fakes are verified against the port too.

Two gaps to close:

- **No check site means no check.** `app.py` normally provides one. To get the error in the adapter's own file, add this
  at the bottom of the adapter module. It never runs; it only makes the checker compare the two:

  ```python
  from typing import TYPE_CHECKING

  if TYPE_CHECKING:
      from sensai.core.ports import LLM

      def _conforms(x: OllamaChat) -> LLM:
          return x   # type error here if OllamaChat doesn't fit LLM
  ```

- **Unannotated methods make the check toothless.** An unannotated parameter is `Any`, which matches anything, and mypy
  skips fully unannotated functions. **Adapter and fake methods must be fully annotated**, with the same types as the
  port.

### End to end: one port, from definition to test

This walkthrough shows the *pattern*. The classes, fields and signatures are simplified examples, not the actual `LLM`
port we'll ship.

**1. Shared models** (`core/models/chat.py`). Ports speak in core types, never library types. See [Models](#models) for
what goes in `models/`.

```python
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class TextDelta:  # one streamed piece of text
    text: str


@dataclass(frozen=True)
class ToolCallRequest:  # the model wants to call a tool
    call: ToolCall


ChatEvent = TextDelta | ToolCallRequest
```

**2. The port** (`core/ports/llm.py`). The error classes live next to the Protocol because "what can go wrong" is part
of the contract.

```python
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from sensai.core.models import ChatEvent, Message, ToolSpec


class LLMError(Exception): ...


class LLMUnavailable(LLMError): ...  # Ollama not running, connection refused


class ModelNotFound(LLMError): ...  # model not pulled


class LLM(Protocol):
    def chat(
            self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[ChatEvent]: ...
```

> **Watch out:** a streaming method is declared with plain `def` returning `AsyncIterator`, even though implementations
> are `async def` with `yield`. Calling an async generator function returns an `AsyncIterator` directly. Writing
> `async def chat(...) -> AsyncIterator[...]` in the Protocol would mean "a coroutine you await to *get* an iterator", and
> no real adapter would match.

**3. The core uses the port.** It asks for it in the constructor, calls it, and catches the port's errors, never a
library's.

```python
# core/agent/loop.py
from sensai.core.models import TextDelta, ToolCallRequest
from sensai.core.ports import LLM, LLMUnavailable


class Agent:
    def __init__(self, llm: LLM, registry: ToolRegistry, bus: EventBus) -> None:
        self._llm = llm
        self._registry = registry
        self._bus = bus

    async def step(self, history: list[Message]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        try:
            async for event in self._llm.chat(history, self._registry.specs()):
                match event:
                    case TextDelta(text):
                        await self._bus.publish(TokenGenerated(text))
                    case ToolCallRequest(call):
                        calls.append(call)
        except LLMUnavailable as e:
            await self._bus.publish(ErrorEvent(str(e)))
        return calls
```

**4. The real adapter** (`adapters/ollama/chat.py`). Its whole job is translation: core models → wire format on the way
out, wire format → core models on the way back, library exceptions → port exceptions.

```python
import json
from collections.abc import AsyncIterator, Sequence

import httpx

from sensai.core.models import ChatEvent, Message, TextDelta, ToolCall, ToolCallRequest, ToolSpec
from sensai.core.ports import LLMUnavailable, ModelNotFound


class OllamaChat:
    def __init__(self, client: httpx.AsyncClient, base_url: str, model: str) -> None:
        self._client, self._url, self._model = client, base_url, model

    async def chat(
            self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[ChatEvent]:
        payload = {
            "model": self._model,
            "messages": [_to_wire(m) for m in messages],
            "tools": [_tool_to_wire(t) for t in tools],
            "stream": True,
        }
        try:
            async with self._client.stream("POST", f"{self._url}/api/chat", json=payload) as r:
                if r.status_code == 404:
                    raise ModelNotFound(self._model)
                r.raise_for_status()
                async for line in r.aiter_lines():
                    msg = json.loads(line).get("message", {})
                    if text := msg.get("content"):
                        yield TextDelta(text)
                    for tc in msg.get("tool_calls", []):
                        fn = tc["function"]
                        yield ToolCallRequest(ToolCall(fn["name"], fn["arguments"]))
        except httpx.ConnectError as e:
            raise LLMUnavailable(f"Cannot reach Ollama at {self._url}") from e
```

This is the only file in the codebase that knows Ollama's endpoint, its streaming format and its tool-call JSON. If
Ollama changes its API, only this file changes.

**5. The fake** (`tests/fakes/llm.py`). It fits the same port but is scripted:

```python
class FakeLLM:
    def __init__(self, turns: list[list[ChatEvent]]) -> None:
        self._turns = iter(turns)
        self.received: list[list[Message]] = []  # for assertions

    async def chat(
            self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[ChatEvent]:
        self.received.append(list(messages))
        for event in next(self._turns):
            yield event
```

**6. A core test**: deterministic, instant, no Ollama needed.

```python
async def test_agent_requests_tool_then_answers():
    llm = FakeLLM([
        [ToolCallRequest(ToolCall("read_file", {"path": "notes.txt"}))],
        [TextDelta("The file says hello.")],
    ])
    agent = Agent(llm, registry=fake_registry(), bus=EventBus())

    calls = await agent.step([Message("user", "What's in notes.txt?")])

    assert calls == [ToolCall("read_file", {"path": "notes.txt"})]
```

With fakes you can script the cases a real model produces only sometimes: a malformed tool call, a missing `send_result`
(the guardrail's injection tripwire), or `LLMUnavailable` raised mid-stream.

**7. Wiring** (`app.py`):

```python
llm = OllamaChat(http, cfg.ollama_url, cfg.model)
agent = Agent(llm, registry, bus)  # the type checker verifies OllamaChat fits LLM here
```

### Rules for writing a good port

- **The core owns it, and it speaks the core's language.** `search(vector, k)`, not `execute_sql(query)` or
  `post_json(url, body)`. If a method name mentions a technology, the abstraction leaks.
- **Minimal.** Only what the core actually calls. Ollama can do a dozen things; `LLM` has one method because the agent
  needs one. Add methods when a caller needs them.
- **Core types in and out.** No library types in signatures.
- **Errors are part of the contract.** Adapters raise port exceptions; the core never catches `httpx` or `sqlite3`
  exceptions.
- **Group by concern.** One module per concern in `core/ports/` (`llm.py`, `retrieval.py`, `memory.py`…), with each
  port's exceptions in the same module. `Embedder` and `VectorStore` share `retrieval.py` because they only make sense
  together.
- **Re-export from `core/ports/__init__.py`** so every caller writes `from sensai.core.ports import LLM`, regardless of
  which module it lives in.

## Models

Data types (dataclasses, enums, type aliases) come in two kinds, and they live in different places.

| Kind       | Definition                                                     | Where it lives             | Examples                                                                                                                     |
|------------|----------------------------------------------------------------|----------------------------|------------------------------------------------------------------------------------------------------------------------------|
| **Shared** | Crosses a boundary: used by a port, or by several core modules | `core/models/<concern>.py` | `Message`, `ToolCall`, `ToolSpec`, `Chunk`                                                                                   |
| **Owned**  | Used by one module only                                        | Next to that module        | `Plan`, `PlanStep` in `core/agent/plan.py`; event types in `core/events/`; a permission grant in `core/tools/permissions.py` |

Keeping owned models next to their owner keeps the code and the data it's about together, and keeps `models/` small.
**When an owned model gets a second user in another module, move it to `models/`.** Moving it is a normal refactor, not
a design failure.

Rules for `core/models/`:

- **Group by concern**, same as ports: `chat.py`, `tools.py`, `retrieval.py`… No `models/message.py` +
  `models/tool_call.py` one-class-per-file split.
- **Re-export from `core/models/__init__.py`** so callers write `from sensai.core.models import Message`.
- **Models are a leaf.** They import only the standard library and each other, never ports, pipeline, agent, tools or
  events. Everything else imports models; if a model imported back, we'd get circular imports. CI enforces this
  (see [Import rules](#import-rules-and-enforcement)).
- **Plain data.** Frozen dataclasses by default, no I/O, no behavior beyond trivial helpers (a `__str__`, a computed
  property). Logic that operates on models lives in the core module that uses it.
- **No library types.** A model never holds an `httpx.Response` or a raw Ollama dict; adapters convert those before
  anything reaches the core.

## Why this structure

| Decision                                | Why                                                                                                                                                                             | What we ruled out                                                                                                                                                  |
|-----------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `src/` layout, installed package        | Tests import the *installed* package, so packaging mistakes fail in CI instead of at demo time. Gives us the `sensai` command via `[project.scripts]`.                          | Flat `main.py` app (not installable, imports work by accident). Flat package at root (tests import the working copy).                                              |
| One package, not a uv workspace         | One team, one release, one process. The TUI and API are two front-ends over the same engine, not separate products.                                                             | Workspace/monorepo: extra config and a shared lockfile constraint for no deployment benefit. We revisit if a component (e.g. our MCP server) must ship separately. |
| Core / adapters split (light hexagonal) | We can test the agent loop and guardrails deterministically with a `FakeLLM`, without Ollama running. Swapping the vector store or adding a front-end doesn't touch core logic. | Layered architecture (core would import the Ollama client directly). Full Clean/Onion (more rings and ceremony than our domain needs).                             |
| Pipeline of uniform stages              | Our request path *is* a pipeline: cache → guard → RAG → agent. A common `Stage` interface makes stages togglable and reorderable, and each feature stays in its own module.     | One big `handle_request()` function with feature flags inside.                                                                                                     |
| Single tool registry                    | Native tools, MCP tools, subagents and memory CRUD share one `call()` path, so permissions and ask/auto mode are enforced in exactly one place.                                 | Per-tool permission checks (easy to forget one).                                                                                                                   |
| Event bus for all output                | The TUI, API and logger consume the same events. Adding a consumer never changes the agent.                                                                                     | Front-ends calling agent internals or passing print callbacks around.                                                                                              |

We don't create a port for everything external; see [When does something get a port?](#when-does-something-get-a-port) A
Protocol with one implementation and no test fake is indirection with no payoff.

## Where does my code go?

| You're writing…                                                                 | Put it in                                                                 | Notes                                                                                                                 |
|---------------------------------------------------------------------------------|---------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| A new request-path feature (filter, enrichment, short-circuit)                  | `core/pipeline/<name>.py`                                                 | Implement `Stage`; wire it in `app.py`.                                                                               |
| A new tool the model can call                                                   | `core/tools/builtin/<name>.py`                                            | If it needs infrastructure (network, subprocess), put the implementation in an adapter and register it from `app.py`. |
| A change to how the agent reasons or loops (ReAct, plan mode)                   | `core/agent/`                                                             | Uses the `LLM` port and the tool registry; tested with `FakeLLM`.                                                     |
| A new event type                                                                | `core/events/`                                                            | Add it to the event union so every consumer sees it.                                                                  |
| A data type used by a port or several core modules                              | `core/models/<concern>.py`                                                | Re-export from `core/models/__init__.py`.                                                                             |
| A data type used by one module only                                             | Next to that module                                                       | Move it to `models/` when it gets a second user.                                                                      |
| Anything that calls Ollama                                                      | `adapters/ollama/`                                                        | The only place allowed to talk to the model.                                                                          |
| Anything that touches SQL, disk formats or HTTP                                 | `adapters/<thing>/`                                                       |                                                                                                                       |
| A new front-end or output consumer                                              | `adapters/<name>/`                                                        | Uses `Engine` + event subscription only.                                                                              |
| A new external dependency the core needs, that tests must fake or we might swap | Protocol in `core/ports/<concern>.py` + adapter + fake in `tests/fakes/`  | All three in the same PR. Re-export from `core/ports/__init__.py`.                                                    |
| A simple stdlib dependency (files, time)                                        | Use it directly in core, or inject a callable                             | No port needed; see [When does something get a port?](#when-does-something-get-a-port)                                |
| A new config option                                                             | `config.py` (schema) + `config/sensai.toml` (default)                     | Read it in `app.py`, pass values down; core never reads config files.                                                 |
| Prompt templates                                                                | Next to the module that uses them (e.g. `core/pipeline/prompts/guard.md`) | Loaded with `importlib.resources`, not relative paths.                                                                |
| A user story                                                                    | `docs/user-stories/<feature>.md`                                          | Required for every feature.                                                                                           |

If none of these fit, ask before creating a new top-level package.

## Recipes

**Add a pipeline stage**

1. Create `core/pipeline/<name>.py` with a class implementing `Stage`.
2. Add tests in `tests/core/pipeline/test_<name>.py` using fakes.
3. Wire it in `app.py`, behind a config toggle if it's optional.
4. Emit events for anything a user or the logger should see.

**Add a port and adapter** (e.g. a new vector store)

1. Add or extend the Protocol in `core/ports/<concern>.py`, with its exception classes, and re-export it from
   `core/ports/__init__.py`.
2. Implement it in `adapters/<name>/`.
3. Add an in-memory fake in `tests/fakes/` so core tests don't need the real thing.
4. Select the implementation in `app.py` from config.

**Add a front-end**

1. Create `adapters/<name>/`.
2. Build the engine with `app.build_engine(cfg)`.
3. Send input with `engine.submit(...)`; render by subscribing to the event bus.
4. If you need data that isn't in an event, add an event. Don't import from `core/agent/` or `core/pipeline/`.

## Import rules and enforcement

The dependency direction is checked in CI with [import-linter](https://import-linter.readthedocs.io/). The contracts
live in `pyproject.toml`:

```toml
[tool.importlinter]
root_package = "sensai"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Core is independent of adapters, wiring and infrastructure libraries"
type = "forbidden"
source_modules = ["sensai.core"]
forbidden_modules = [
    "sensai.adapters",
    "sensai.app",
    "sensai.cli",
    "httpx",
    "fastapi",
]

[[tool.importlinter.contracts]]
name = "Models are a leaf: they import nothing else from the core"
type = "forbidden"
source_modules = ["sensai.core.models"]
forbidden_modules = [
    "sensai.core.ports",
    "sensai.core.pipeline",
    "sensai.core.agent",
    "sensai.core.tools",
    "sensai.core.events",
    "sensai.core.engine",
]

[[tool.importlinter.contracts]]
name = "Adapters do not import each other"
type = "independence"
modules = [
    "sensai.adapters.ollama",
    "sensai.adapters.vectorstore",
    "sensai.adapters.memory",
    "sensai.adapters.mcp",
    "sensai.adapters.sandbox",
    "sensai.adapters.tui",
    "sensai.adapters.api",
]
```

Run it locally with `uv run lint-imports`. Add new adapter packages and infrastructure libraries to these lists when you
introduce them.

Other import conventions:

- Absolute imports only (`from sensai.core.ports import LLM`), no relative `..` imports across packages.
- A package's `__init__.py` re-exports its public names; other packages import from there, not from private modules.
- Modules and functions prefixed with `_` are private to their package.

## Packages and `__init__.py`

**Every directory of Python code gets an `__init__.py`**, in `src/sensai/` and in `tests/`.

Python can import folders without one (implicit namespace packages, PEP 420), but we don't rely on that:

- `uv_build` expects `src/sensai/__init__.py` to find the package.
- Type checkers, pytest and import-linter resolve module names inconsistently for namespace packages, which produces
  confusing "module not found" or duplicate-module errors.
- Namespace packages exist to split one package across several distributions. We ship one distribution, so we get the
  drawbacks without the benefit.

In `tests/`, the `__init__.py` files also prevent name collisions: `tests/core/pipeline/test_base.py` and
`tests/adapters/tui/test_base.py` would otherwise both import as `test_base` and pytest would refuse to collect one of
them.

What goes inside:

- **Most `__init__.py` files are empty.**
- **A package with a public API re-exports it**, so callers don't depend on internal module layout:

  ```python
  # src/sensai/core/pipeline/__init__.py
  from sensai.core.pipeline.base import Pipeline, Stage
  from sensai.core.pipeline.cache import SemanticCache
  from sensai.core.pipeline.guard import PromptGuard
  from sensai.core.pipeline.rag import RagInjector

  __all__ = ["Pipeline", "Stage", "SemanticCache", "PromptGuard", "RagInjector"]
  ```

- **No logic, no side effects, no heavy imports.** An `__init__.py` must not open connections, read config, register
  tools or import optional extras like FastAPI; importing `sensai.adapters` must work on an install without the `web`
  extra. Registration and wiring happen in `app.py`.

## Naming

- Modules and packages: `snake_case`, singular nouns for things (`registry.py`, `guard.py`), no `utils.py` or
  `helpers.py`. If you're about to create one, the code belongs next to whatever uses it.
- Ports are named for the role (`LLM`, `VectorStore`); adapters for the technology (`OllamaChat`, `SqliteVectorStore`).
- Test files mirror the source path: `src/sensai/core/pipeline/guard.py` → `tests/core/pipeline/test_guard.py`.

## Dependencies

- Runtime deps go in `[project.dependencies]`; front-end-specific ones in extras (`web`, `tui`); tooling in
  `[dependency-groups] dev`.
- Add with `uv add <pkg>` (or `uv add --optional web <pkg>`, `uv add --dev <pkg>`), never by editing `uv.lock`.
- No LLM frameworks (LangChain, LlamaIndex, Haystack…). This is a project rule: model calls go through our own Ollama
  adapter.

## PR checklist

- [ ] New code is in the zone the table above says it belongs to.
- [ ] Every new directory has an `__init__.py` with no side effects.
- [ ] `uv run lint-imports` passes.
- [ ] Any new port has an adapter **and** a fake in `tests/fakes/`.
- [ ] Adapter and fake methods are fully annotated, and the type checker passes.
- [ ] Adapters only translate: no decisions, no retries with reworded prompts, no filtering logic.
- [ ] No library types (`httpx`, `sqlite3`, Ollama JSON…) in core signatures.
- [ ] New wiring and toggles are in `app.py`, not in core modules.
- [ ] Tests mirror the source path.
- [ ] Any new feature has a user story in `docs/user-stories/`.
