"""Tests for finding the session model among the loaded ones."""

from __future__ import annotations

import asyncio

from sensai.core.model_memory import ModelMemory
from sensai.core.models.llm import LoadedModel
from tests.fakes import FakeModelMonitor


def _loaded(name: str) -> LoadedModel:
    return LoadedModel(name=name, size_bytes=10, vram_bytes=8)


def _current(monitor: FakeModelMonitor, model: str) -> LoadedModel | None:
    return asyncio.run(ModelMemory(monitor, model).current())


def test_the_configured_model_is_picked() -> None:
    """Other loaded models, like the embedding one, are ignored."""
    monitor = FakeModelMonitor(_loaded("nomic-embed-text:latest"), _loaded("qwen3:8b"))

    assert _current(monitor, "qwen3:8b") == _loaded("qwen3:8b")


def test_a_name_without_tag_means_latest() -> None:
    """`qwen3` and `qwen3:latest` are the same model, in either direction."""
    assert _current(FakeModelMonitor(_loaded("qwen3:latest")), "qwen3") is not None
    assert _current(FakeModelMonitor(_loaded("qwen3")), "qwen3:latest") is not None


def test_another_tag_is_another_model() -> None:
    """`qwen3` does not match a loaded `qwen3:8b`."""
    assert _current(FakeModelMonitor(_loaded("qwen3:8b")), "qwen3") is None


def test_a_model_that_is_not_loaded_gives_none() -> None:
    """The server may have unloaded an idle model."""
    assert _current(FakeModelMonitor(), "qwen3:8b") is None


def test_names_are_compared_without_case() -> None:
    """`llama3.2:3B` finds `llama3.2:3b`, as Ollama ignores the case too."""
    monitor = FakeModelMonitor(_loaded("llama3.2:3b"))

    assert _current(monitor, "llama3.2:3B") == _loaded("llama3.2:3b")
