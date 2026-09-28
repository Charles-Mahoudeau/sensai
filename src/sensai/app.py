"""Main application code."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from sensai.adapters.ollama import OllamaChat
from sensai.config import Config, load_config
from sensai.core.agent import Agent
from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.pipeline.base import Pipeline

if TYPE_CHECKING:
    import pathlib

    import httpx

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

    print("Sensai config:", config)


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
