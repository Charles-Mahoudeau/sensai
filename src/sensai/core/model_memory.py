"""Find the memory footprint of the model a session chats with."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensai.core.models.llm import LoadedModel
    from sensai.core.ports import ModelMonitor

_DEFAULT_TAG = "latest"


class ModelMemory:
    """Pick one model out of everything a model server has loaded."""

    def __init__(self, monitor: ModelMonitor, model: str) -> None:
        """Store the monitor and the model to look for.

        Args:
            monitor: Lists the models the server has loaded.
            model: The model name, with or without its tag.
        """
        self._monitor = monitor
        self._model = _with_tag(model)

    async def current(self) -> LoadedModel | None:
        """Return the model's footprint, or `None` if it is not loaded right now.

        Raises:
            LLMUnavailableError: The model server cannot be reached.
            LLMResponseError: The server's response cannot be understood.
        """
        for loaded in await self._monitor.loaded_models():
            if _with_tag(loaded.name) == self._model:
                return loaded
        return None


def _with_tag(name: str) -> str:
    """Add the tag a server assumes when none is given (`qwen3` → `qwen3:latest`)."""
    return name if ":" in name else f"{name}:{_DEFAULT_TAG}"
