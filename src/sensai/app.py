"""Main application code."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from dotenv import load_dotenv

from sensai.adapters.cli import PromptCommands
from sensai.adapters.http import BearerAuth
from sensai.adapters.mcp.http_client import HttpMcpClient
from sensai.adapters.ollama import OllamaChat, OllamaMonitor
from sensai.adapters.persona import TomlPersonaDir
from sensai.adapters.profile import read_profile_file
from sensai.adapters.storage import sqlite_migrator
from sensai.adapters.storage.connection import create_connection
from sensai.adapters.storage.repositories import (
    SqliteMemoryRepository,
    SqliteProfileRepository,
    SqlitePromptRepository,
    SqliteSessionRepository,
)
from sensai.adapters.storage.sqlite import SqliteDatabase
from sensai.adapters.tui import SensaiApp
from sensai.adapters.tui.commands.builtin import default_registry
from sensai.config import Config, load_config
from sensai.core.agent.memory_extraction import MemoryExtractor
from sensai.core.agent.memory_recall import MemoryRecall
from sensai.core.agent.prompts import AgentPrompts, MemoryPrompts
from sensai.core.agent.re_act import ReActAgent
from sensai.core.agent.session_title import SessionTitler
from sensai.core.agent.structured import StructuredOutputCatalog
from sensai.core.engine import Engine
from sensai.core.errors import SensaiError
from sensai.core.events import EventBus
from sensai.core.model_memory import ModelMemory
from sensai.core.pipeline.base import Pipeline
from sensai.core.profile import render_profile
from sensai.core.prompts import (
    SESSION_TITLE,
    PromptComparison,
    PromptLibrary,
    load_defaults,
)
from sensai.core.sessions import SessionRecorder
from sensai.core.tools.builtin import calculator, memory, web_search
from sensai.core.tools.mcp import register_mcp_server
from sensai.core.tools.registry import ToolRegistry
from sensai.core.usage import MeteredLLM, UsageMeter

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable, Sequence

    from sensai.core.agent import Agent
    from sensai.core.models import McpServerStatus, Message
    from sensai.core.ports import (
        LLM,
        McpClient,
        MemoryRepository,
        ModelMonitor,
        SessionRepository,
    )


@dataclass(frozen=True)
class ChatOptions:
    """How the chat starts, as chosen on the command line.

    Attributes:
        tools_enabled: Whether the tools start enabled; they can still be
            toggled from the TUI.
    """

    tools_enabled: bool = True


# So this function will be call at start and the engine will be built
# and returned for the TUI or CLI to use.
async def build_engine(
    config: Config,
    agent: Agent,
    system_prompt: str,
    history: Sequence[Message] = (),
    *,
    profile: str = "",
    tools: ToolRegistry | None = None,
    mcp_servers: Sequence[McpServerStatus] = (),
    monitor: ModelMonitor | None = None,
    usage_meter: UsageMeter | None = None,
    sessions: SessionRepository | None = None,
) -> Engine:
    """Build an Engine around an already configured agent.

    Args:
        config: The application configuration, for the personas.
        agent: The agent that runs each turn, as built by `build_agent`.
        system_prompt: The base system prompt, before the persona.
        history: Messages restored from a previous session.
        profile: The rendered user profile, after the persona.
        tools: The agent's tools, so front-ends can list and toggle them.
        mcp_servers: The outcome of connecting to each MCP server.
        monitor: Reports the memory used by the configured model, if any.
        usage_meter: The meter the agent's model counts into, if any.
        sessions: Where the sessions are stored, for front-ends to list them.

    Returns:
        The engine, ready to be driven by the TUI or CLI.

    Raises:
        PersonaError: The default persona is missing or not valid.
    """
    engine = Engine(
        runner=agent,
        pipeline=Pipeline(),
        bus=EventBus(),
        system_prompt=system_prompt,
        profile=profile,
        personas=TomlPersonaDir(config.personas.path),
        history=history,
        tools=tools,
        mcp_servers=mcp_servers,
        model_memory=ModelMemory(monitor, config.model) if monitor else None,
        usage_meter=usage_meter,
        sessions=sessions,
    )
    if config.personas.default is not None:
        engine.set_persona(config.personas.default)
    return engine


async def build_tools(
    config: Config,
    stack: contextlib.AsyncExitStack,
    memory_repository: MemoryRepository,
) -> tuple[ToolRegistry, tuple[McpServerStatus, ...]]:
    """Build the tool registry: the built-in tools, then each MCP server's.

    A server that cannot be reached is skipped and reported in its status.

    Args:
        config: The application configuration.
        stack: Closes the MCP clients when the app exits.
        memory_repository: Where the memory tools store and read records.

    Returns:
        The registry, and the outcome of connecting to each MCP server.
    """
    tool_registry = ToolRegistry()
    web_search.register_self(tool_registry)
    calculator.register_self(tool_registry)
    memory.register_self(tool_registry, memory_repository)

    clients: list[McpClient] = []
    for server in config.mcp.servers:
        if server.token_env and not server.token:
            logging.getLogger(__name__).warning(
                "%s not set, skipping the %s MCP server", server.token_env, server.name
            )
            continue
        auth = BearerAuth(server.token) if server.token else None
        clients.append(HttpMcpClient(server.name, server.url, auth))

    statuses: list[McpServerStatus] = []
    for client in clients:
        stack.push_async_callback(client.aclose)
        statuses.append(await register_mcp_server(tool_registry, client))
    return tool_registry, tuple(statuses)


async def build_agent(
    config: Config,
    client: httpx.AsyncClient,
    tool_registry: ToolRegistry,
    agent_prompts: AgentPrompts | None = None,
    memory_repository: MemoryRepository | None = None,
    memory_prompts: MemoryPrompts | None = None,
    usage_meter: UsageMeter | None = None,
) -> ReActAgent:
    """Build the ReAct agent around its tools.

    Args:
        config: The application configuration.
        client: The HTTP client used by the Ollama adapter.
        tool_registry: The tools offered to the model, as built by `build_tools`.
        agent_prompts: Prompts overriding the agent's defaults, if any.
        memory_repository: Where the agent records what the user says about
            themself and recalls it from; no automatic memory when `None`.
        memory_prompts: Prompts overriding the memory defaults, if any.
        usage_meter: Counts the tokens of every model call; none if `None`.

    Returns:
        The agent.
    """
    llm: LLM = _ollama_chat(config, client)
    if usage_meter is not None:
        llm = MeteredLLM(llm, usage_meter)
    memory_prompts = memory_prompts or MemoryPrompts.defaults()
    structured_output = (
        StructuredOutputCatalog(config.structured_output.schemas)
        if config.structured_output.enabled
        else None
    )
    agent = ReActAgent(
        llm,
        tool_registry,
        agent_prompts,
        structured_output=structured_output,
        memory_extractor=(
            MemoryExtractor(llm, memory_repository, memory_prompts.extraction)
            if memory_repository
            else None
        ),
        memory_recall=(
            MemoryRecall(memory_repository, title=memory_prompts.recall)
            if memory_repository
            else None
        ),
    )
    agent.thinking_effort = config.agent.thinking_effort
    return agent


def _ollama_chat(config: Config, client: httpx.AsyncClient) -> OllamaChat:
    return OllamaChat(
        client,
        config.ollama.url,
        config.model,
        keep_alive=config.ollama.keep_alive,
    )


async def _preload(chat: OllamaChat) -> None:
    """Load the model; if it fails, the first answer only loads it instead."""
    try:
        await chat.load()
    except SensaiError as e:
        logging.getLogger(__name__).warning("could not preload the model: %s", e)


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def main(
    model: str, config_path: pathlib.Path, options: ChatOptions | None = None
) -> None:
    """Application entrypoint.

    Args:
        model: The model name.
        config_path: The path to the configuration file.
        options: How the chat starts; the defaults when `None`.

    Returns:
        None
    """
    logging.basicConfig(level=logging.INFO, filename="sensai.log")
    load_dotenv()
    config = _parse_config(model, config_path)

    asyncio.run(_serve(config, options or ChatOptions()))


def _get_db() -> SqliteDatabase:
    """Get the SQLite database."""
    conn = create_connection()
    sqlite_migrator.apply_migrations(conn)
    return SqliteDatabase(conn)


async def _get_profile_sys_prompt(config: Config, db: SqliteDatabase) -> str:
    profile_repo = SqliteProfileRepository(db)
    wanted = read_profile_file(config.user_profile.profile)
    for category, entries in wanted.items():
        for key, value in entries.items():
            await profile_repo.set_profile_value(key, value, category=category)
    system_prompt = render_profile(await profile_repo.find())
    return system_prompt


async def _get_prompt_library(db: SqliteDatabase) -> PromptLibrary:
    library = PromptLibrary(SqlitePromptRepository(db))
    await library.sync_defaults(load_defaults())
    return library


async def _serve(config: Config, options: ChatOptions) -> None:
    async with (
        httpx.AsyncClient(timeout=None) as client,
        contextlib.AsyncExitStack() as stack,
    ):
        # Load the model while the rest starts up; stopped before the client closes.
        preload = asyncio.create_task(_preload(_ollama_chat(config, client)))
        stack.push_async_callback(_cancel, preload)
        db = _get_db()

        prompts = await _get_prompt_library(db)
        profile = await _get_profile_sys_prompt(config, db)
        system_prompt = await prompts.system_prompt()
        agent_prompts = await AgentPrompts.active(prompts)
        memory_prompts = await MemoryPrompts.active(prompts)

        session_repo = SqliteSessionRepository(db)
        memory_repo = SqliteMemoryRepository(db)
        usage_meter = UsageMeter()

        tools, mcp_servers = await build_tools(config, stack, memory_repo)
        tools.set_all_enabled(enabled=options.tools_enabled)
        agent = await build_agent(
            config,
            client,
            tools,
            agent_prompts,
            memory_repo,
            memory_prompts,
            usage_meter=usage_meter,
        )
        engine = await build_engine(
            config,
            agent,
            system_prompt,
            profile=profile,
            tools=tools,
            mcp_servers=mcp_servers,
            monitor=OllamaMonitor(client, config.ollama.url),
            usage_meter=usage_meter,
            sessions=session_repo,
        )
        # The unmetered model: naming a session is not part of its usage.
        titler = SessionTitler(
            _ollama_chat(config, client),
            (await prompts.active(SESSION_TITLE)).content,
        )
        recorder = SessionRecorder(
            session_repo,
            engine,
            model=config.model,
            session_id=None,
            saved=0,
            meter=usage_meter,
            titler=titler,
        )
        watcher = asyncio.create_task(recorder.watch())
        await asyncio.sleep(0)  # subscribed before the first message
        commands = default_registry(
            on_clear=recorder.start_new,
            on_resume=recorder.resume,
            persona_names=engine.persona_names,
        )
        await SensaiApp(engine, model=config.model, commands=commands).run_async()
        await _cancel(watcher)
        await recorder.save()


def prompts_list() -> None:
    """Print every prompt with its active version."""
    _run_prompt_command(lambda commands: commands.list())


def prompts_history(name: str) -> None:
    """Print every version of a prompt.

    Args:
        name: The prompt name.
    """
    _run_prompt_command(lambda commands: commands.history(name))


def prompts_show(name: str, version: int | None) -> None:
    """Print one version of a prompt.

    Args:
        name: The prompt name.
        version: The version to print; the active one when `None`.
    """
    _run_prompt_command(lambda commands: commands.show(name, version))


def prompts_new(name: str, file: pathlib.Path, note: str | None) -> None:
    """Save a file as the new active version of a prompt.

    Args:
        name: The prompt name.
        file: The file holding the new text.
        note: What changed in this version.
    """
    _run_prompt_command(lambda commands: commands.new(name, file, note))


def prompts_diff(name: str, old: int, new: int) -> None:
    """Print the changes between two versions of a prompt.

    Args:
        name: The prompt name.
        old: The version to diff from.
        new: The version to diff to.
    """
    _run_prompt_command(lambda commands: commands.diff(name, old, new))


def prompts_rollback(name: str, version: int) -> None:
    """Make an older version of a prompt active again.

    Args:
        name: The prompt name.
        version: The version to activate.
    """
    _run_prompt_command(lambda commands: commands.rollback(name, version))


def prompts_compare(
    name: str,
    versions: tuple[int, int],
    inputs: pathlib.Path,
    *,
    model: str,
    config_path: pathlib.Path,
    judge: bool,
    output: pathlib.Path | None,
) -> None:
    """Run two versions of a prompt on the same inputs and print the comparison.

    Args:
        name: The prompt name.
        versions: The two versions to compare.
        inputs: A text file with one input per line.
        model: The model that answers (and judges).
        config_path: The path to the configuration file.
        judge: Whether the model also judges which answer is better.
        output: Where to save the full report as JSON, if anywhere.
    """
    config = _parse_config(model, config_path)

    async def compare(commands: PromptCommands) -> None:
        # Fail fast if Ollama can't be reached; a slow answer may take minutes.
        timeout = httpx.Timeout(None, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            llm = _ollama_chat(config, client)
            await commands.compare(
                PromptComparison(llm, time.perf_counter),
                name,
                versions,
                inputs,
                judge=judge,
                output=output,
            )

    _run_prompt_command(compare)


def _run_prompt_command(
    command: Callable[[PromptCommands], Awaitable[None]],
) -> None:
    """Run one prompt command; report expected failures as `error: …`, exit 1."""

    async def run() -> None:
        await command(PromptCommands(await _get_prompt_library(_get_db())))

    try:
        asyncio.run(run())
    except (SensaiError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


def _parse_config(model: str, config_path: pathlib.Path) -> Config:
    try:
        config = load_config(config_path, {"model": model})
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    if config.model == "":
        print("error: model not specified", file=sys.stderr)
        raise SystemExit(1)

    return config
