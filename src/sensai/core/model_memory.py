"""Find the memory footprint and context window of the model a session uses."""

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
            monitor: Lists the models the server has loaded, and their details.
            model: The model name, with or without its tag.
        """
        self._monitor = monitor
        self._name = model
        self._model = _with_tag(model)
        self._max_context: int | None = None
        self._max_context_read = False

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

    async def max_context(self) -> int | None:
        """Return the largest context window the model supports, if known.

        It is read from the server once, then kept: it never changes.

        Raises:
            LLMUnavailableError: The model server cannot be reached.
            ModelNotFoundError: The model does not exist on the server.
            LLMResponseError: The server's response cannot be understood.
        """
        if not self._max_context_read:
            self._max_context = await self._monitor.max_context_length(self._name)
            self._max_context_read = True
        return self._max_context


def _with_tag(name: str) -> str:
    """Add the tag a server assumes when none is given (`qwen3` → `qwen3:latest`)."""
    name = name.casefold()
    return name if ":" in name else f"{name}:{_DEFAULT_TAG}"
