"""Tests for the application composition root."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from sensai.app import build_agent, build_engine
from sensai.config import Config, OllamaConfig, ProfileConfig
from sensai.core.engine import Engine
from sensai.core.models.llm import LoadedModel
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeModelMonitor


def test_build_engine_wires_the_configured_ollama_client() -> None:
    """The composition root creates an Engine without contacting Ollama."""

    async def run() -> None:
        config = Config(
            model="test-model",
            ollama=OllamaConfig("http://ollama"),
            user_profile=ProfileConfig(profile=Path()),
        )
        async with httpx.AsyncClient() as client:
            agent = await build_agent(config, client, ToolRegistry())
            engine = await build_engine(config, agent, "")

            assert isinstance(engine, Engine)

    asyncio.run(run())


def test_build_engine_reads_the_configured_model_from_the_monitor() -> None:
    """The engine reports the memory of the configured model, not another one."""
    model = LoadedModel(name="test-model:latest", size_bytes=10, vram_bytes=10)
    monitor = FakeModelMonitor(
        LoadedModel(name="nomic-embed-text:latest", size_bytes=1, vram_bytes=1), model
    )

    async def run() -> LoadedModel | None:
        config = Config(
            model="test-model",
            ollama=OllamaConfig("http://ollama"),
            user_profile=ProfileConfig(profile=Path()),
        )
        async with httpx.AsyncClient() as client:
            agent = await build_agent(config, client, ToolRegistry())
            engine = await build_engine(config, agent, "", monitor=monitor)
            return await engine.loaded_model()

    assert asyncio.run(run()) == model
