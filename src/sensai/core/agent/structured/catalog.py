"""Catalog of structured output contracts available to an agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from sensai.core.agent.structured.validation import JsonSchemaOutput

if TYPE_CHECKING:
    from collections.abc import Mapping

type OutputSchemaName = Literal["permission_decision", "plan"]


class StructuredOutputCatalog:
    """Select JSON Schema validators for agent output contexts."""

    def __init__(self, schemas: Mapping[str, Mapping[str, Any]]) -> None:
        """Store one independent validator for each output context."""
        self._outputs = {
            name: JsonSchemaOutput(schema) for name, schema in schemas.items()
        }

    def select(self, name: OutputSchemaName) -> JsonSchemaOutput:
        """Return the validator chosen by the agent's current context."""
        try:
            return self._outputs[name]
        except KeyError as error:
            raise ValueError(f"missing structured output schema: {name}") from error
