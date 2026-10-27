"""Fake implementing the model monitor port."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.llm import LoadedModel


class FakeModelMonitor:
    """Report a fixed list of loaded models; tests change it through `models`.

    Implements the `ModelMonitor` port.
    """

    def __init__(self, *models: LoadedModel) -> None:
        """Start with the given models loaded."""
        self.models = list(models)

    async def loaded_models(self) -> Sequence[LoadedModel]:
        """Every model currently loaded."""
        return tuple(self.models)
