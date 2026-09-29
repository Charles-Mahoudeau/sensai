"""Main application code."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import httpx

from sensai.adapters.ollama import OllamaChat
from sensai.adapters.tui import SensaiApp
from sensai.config import Config, load_config
from sensai.core.agent import Agent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.pipeline.base import Pipeline

if TYPE_CHECKING:
    import pathlib

    from sensai.core.ports import LLM


# So this function will be call at start and the engine will be built
# and returned for the TUI or CLI to use.
def build_engine(config: Config, client: httpx.AsyncClient) -> Engine:
    """Build an Engine using the configured Ollama adapter."""
    llm: LLM = OllamaChat(client, config.ollama.url, config.model)
    return Engine(
        runner=Agent(llm),
        pipeline=Pipeline(),
        bus=EventBus(),
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


async def _serve(config: Config) -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        engine = build_engine(config, client)
        await SensaiApp(engine, model=config.model).run_async()


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
