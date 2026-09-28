"""Tests for the application composition root."""

from __future__ import annotations

import asyncio

import httpx

from sensai.app import build_engine
from sensai.config import Config, OllamaConfig
from sensai.core.engine import Engine


def test_build_engine_wires_the_configured_ollama_client() -> None:
    """The composition root creates an Engine without contacting Ollama."""

    async def run() -> None:
        config = Config(model="test-model", ollama=OllamaConfig("http://ollama"))
        async with httpx.AsyncClient() as client:
            engine = build_engine(config, client)

            assert isinstance(engine, Engine)

    asyncio.run(run())
