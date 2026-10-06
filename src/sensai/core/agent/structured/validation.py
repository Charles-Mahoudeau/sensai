"""JSON parsing and schema-subset validation for structured agent output."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from collections.abc import Mapping


class StructuredOutputError(SensaiError):
    """Raised when a model response does not meet its requested schema."""


class JsonSchemaOutput:
    """Constrain a structured response to a configured JSON Schema subset."""

    def __init__(self, schema: Mapping[str, Any]) -> None:
        """Store an isolated copy of the schema used for generation and validation."""
        self._schema = deepcopy(dict(schema))

    @property
    def schema(self) -> dict[str, Any]:
        """Return a copy of the JSON Schema sent to the model."""
        return deepcopy(self._schema)

    def validate(self, content: str) -> None:
        """Raise when content is not a valid instance of the configured schema."""
        self.parse(content)

    def parse(self, content: str) -> Any:
        """Parse and validate content, then return its JSON value."""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise StructuredOutputError("model response is not valid JSON") from error

        self._validate_value(parsed, self._schema, "response")
        return parsed

    def _validate_value(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate the JSON Schema keywords used by Sensai's bundled schemas."""
        if "enum" in schema and value not in schema["enum"]:
            raise StructuredOutputError(f"{path} must be one of {schema['enum']!r}")

        schema_type = schema.get("type")
        if schema_type == "object":
            self._validate_object(value, schema, path)
        elif schema_type == "array":
            self._validate_array(value, schema, path)
        elif schema_type == "string" and not isinstance(value, str):
            raise StructuredOutputError(f"{path} must be a string")
        elif schema_type == "boolean" and not isinstance(value, bool):
            raise StructuredOutputError(f"{path} must be a boolean")
        elif schema_type == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise StructuredOutputError(f"{path} must be an integer")
        elif schema_type == "number" and (
            not isinstance(value, int | float) or isinstance(value, bool)
        ):
            raise StructuredOutputError(f"{path} must be a number")

        if "minimum" in schema and value < schema["minimum"]:
            raise StructuredOutputError(f"{path} must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise StructuredOutputError(f"{path} must be at most {schema['maximum']}")

    def _validate_object(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate object properties and reject unrequested fields."""
        if not isinstance(value, dict):
            raise StructuredOutputError(f"{path} must be a JSON object")

        properties = schema.get("properties", {})
        missing = set(schema.get("required", ())) - set(value)
        if missing:
            names = ", ".join(sorted(missing))
            raise StructuredOutputError(f"{path} is missing required field(s): {names}")
        if schema.get("additionalProperties") is False:
            unexpected = set(value) - set(properties)
            if unexpected:
                names = ", ".join(sorted(unexpected))
                raise StructuredOutputError(f"{path} has unexpected field(s): {names}")
        for name, property_schema in properties.items():
            if name in value:
                self._validate_value(value[name], property_schema, f"{path}.{name}")

    def _validate_array(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate arrays and every item against their item schema."""
        if not isinstance(value, list):
            raise StructuredOutputError(f"{path} must be an array")
        if len(value) < schema.get("minItems", 0):
            raise StructuredOutputError(
                f"{path} must contain at least {schema['minItems']} item(s)"
            )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                self._validate_value(item, item_schema, f"{path}[{index}]")
