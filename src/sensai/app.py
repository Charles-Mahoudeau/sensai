"""Main application code."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import TYPE_CHECKING

import httpx

from sensai.adapters.cli import PromptCommands
from sensai.adapters.ollama import OllamaChat
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
from sensai.config import Config, load_config
from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.re_act import ReActAgent
from sensai.core.engine import Engine
from sensai.core.errors import SensaiError
from sensai.core.events import EventBus
from sensai.core.pipeline.base import Pipeline
from sensai.core.profile import render_profile
from sensai.core.prompts import PromptComparison, PromptLibrary, load_defaults
from sensai.core.tools.builtin import memory, web_search
from sensai.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable, Sequence

    from sensai.core.models import Message
    from sensai.core.ports import LLM, MemoryRepository


# tools are register at app level instead of agent level
def register_tools(
    tool_registry: ToolRegistry, memory_repository: MemoryRepository
) -> None:
    """Register built-in tools with the given tool registry and memory repository."""
    web_search.register_self(tool_registry)
    memory.register_self(tool_registry, memory_repository)


# So this function will be call at start and the engine will be built
# and returned for the TUI or CLI to use.
def build_engine(
    config: Config,
    client: httpx.AsyncClient,
    system_prompt: str,
    history: Sequence[Message] = (),
    *,
    memory_repository: MemoryRepository,
    agent_prompts: AgentPrompts | None = None,
) -> Engine:
    """Build an Engine using the configured Ollama adapter."""
    llm: LLM = OllamaChat(client, config.ollama.url, config.model)
    tool_registry = ToolRegistry()
    register_tools(tool_registry, memory_repository)
    agent = ReActAgent(llm, tool_registry, prompts=agent_prompts)
    return Engine(
        runner=agent,
        pipeline=Pipeline(),
        bus=EventBus(),
        system_prompt=system_prompt,
        history=history,
    )


def main(model: str, config_path: pathlib.Path) -> None:
    """Application entrypoint.

    Args:
        model: The model name.
        config_path: The path to the configuration file.

    Returns:
        None
    """
    logging.basicConfig(level=logging.INFO, filename="sensai.log")
    config = _parse_config(model, config_path)

    asyncio.run(_serve(config))


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


async def _serve(config: Config) -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        db = _get_db()

        prompts = await _get_prompt_library(db)
        profile = await _get_profile_sys_prompt(config, db)
        system_prompt = await prompts.system_prompt(profile)
        agent_prompts = await AgentPrompts.active(prompts)

        session_repo = SqliteSessionRepository(db)
        memory_repo = SqliteMemoryRepository(db)
        last = await session_repo.list_sessions(limit=1)
        session = (
            last[0] if last else await session_repo.create_session(model=config.model)
        )
        history = await session_repo.get_messages(session.id)

        engine = build_engine(
            config,
            client,
            system_prompt,
            history,
            memory_repository=memory_repo,
            agent_prompts=agent_prompts,
        )
        await SensaiApp(engine, model=config.model).run_async()

        for message in engine.history[len(history) :]:
            await session_repo.append_message(session.id, message)


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
            llm = OllamaChat(client, config.ollama.url, config.model)
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
