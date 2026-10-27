"""Fake implementing the model monitor port."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.llm import LoadedModel
    from sensai.core.ports import ModelMonitor


class FakeModelMonitor:
    """Report fixed loaded models and context window; tests change both.

    Implements the `ModelMonitor` port. `show_calls` counts the reads of the
    context window, so tests can check that it is cached.
    """

    def __init__(self, *models: LoadedModel, max_context: int | None = None) -> None:
        """Start with the given models loaded, all supporting `max_context`."""
        self.models = list(models)
        self.max_context = max_context
        self.show_calls = 0

    async def loaded_models(self) -> Sequence[LoadedModel]:
        """Every model currently loaded."""
        return tuple(self.models)

    async def max_context_length(self, model: str) -> int | None:
        """The configured maximum, whatever the model."""
        del model
        self.show_calls += 1
        return self.max_context


if TYPE_CHECKING:

    def _conforms(fake: FakeModelMonitor) -> ModelMonitor:
        return fake
