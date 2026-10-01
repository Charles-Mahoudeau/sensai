"""Main application code."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import httpx

from sensai.adapters.ollama import OllamaChat
from sensai.adapters.profile import read_profile_file
from sensai.adapters.storage import sqlite_migrator
from sensai.adapters.storage.connection import create_connection
from sensai.adapters.storage.repositories import (
    SqliteProfileRepository,
    SqliteSessionRepository,
)
from sensai.adapters.storage.sqlite import SqliteDatabase
from sensai.adapters.tui import SensaiApp
from sensai.config import Config, load_config
from sensai.core.agent import Agent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.pipeline.base import Pipeline
from sensai.core.profile import render_profile

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

    from sensai.core.models import Message
    from sensai.core.ports import LLM


# So this function will be call at start and the engine will be built
# and returned for the TUI or CLI to use.
def build_engine(
    config: Config,
    client: httpx.AsyncClient,
    system_prompt: str,
    history: Sequence[Message] = (),
) -> Engine:
    """Build an Engine using the configured Ollama adapter."""
    llm: LLM = OllamaChat(client, config.ollama.url, config.model)
    return Engine(
        runner=Agent(llm),
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


async def _serve(config: Config) -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        db = _get_db()

        system_prompt = await _get_profile_sys_prompt(config, db)

        session_repo = SqliteSessionRepository(db)
        last = await session_repo.list_sessions(limit=1)
        session = (
            last[0] if last else await session_repo.create_session(model=config.model)
        )
        history = await session_repo.get_messages(session.id)

        engine = build_engine(config, client, system_prompt, history)
        await SensaiApp(engine, model=config.model).run_async()

        for message in engine.history[len(history) :]:
            await session_repo.append_message(session.id, message)


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
