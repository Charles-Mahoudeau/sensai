"""JSON parsing and schema-subset validation for structured agent output."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar

from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


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

        self.check(parsed, "response")
        return parsed

    def check(self, value: Any, path: str = "value") -> None:
        """Validate a value that is already parsed, such as tool call arguments.

        Keywords outside the supported subset are ignored, so a schema written
        for another validator, such as an MCP tool's, accepts more than it
        should rather than rejecting a valid value.

        Raises:
            StructuredOutputError: The value breaks a supported keyword.
        """
        self._validate_value(value, self._schema, path)

    def _validate_value(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate the JSON Schema keywords used by Sensai's bundled schemas."""
        if schema is False:
            raise StructuredOutputError(f"{path} is not allowed")
        if not isinstance(schema, dict):
            return  # `true`: accepts any value
        if "enum" in schema and value not in schema["enum"]:
            raise StructuredOutputError(f"{path} must be one of {schema['enum']!r}")

        type_ = schema.get("type")
        if isinstance(type_, list):
            self._validate_any_type(value, schema, type_, path)
        else:
            validator = (
                self._TYPE_VALIDATORS.get(type_) if isinstance(type_, str) else None
            )
            if validator is not None:
                validator(self, value, schema, path)

        if not isinstance(value, int | float) or isinstance(value, bool):
            return
        if "minimum" in schema and value < schema["minimum"]:
            raise StructuredOutputError(f"{path} must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise StructuredOutputError(f"{path} must be at most {schema['maximum']}")

    def _validate_any_type(
        self, value: Any, schema: dict[str, Any], types: list[Any], path: str
    ) -> None:
        """Validate a value against a list of types, such as `["string", "null"]`."""
        for type_ in types:
            if type_ == "null":
                if value is None:
                    return
                continue
            validator = (
                self._TYPE_VALIDATORS.get(type_) if isinstance(type_, str) else None
            )
            if validator is None:
                return  # a type this validator doesn't know: not checked
            try:
                validator(self, value, schema, path)
            except StructuredOutputError:
                continue
            return
        raise StructuredOutputError(f"{path} must be one of the types {types!r}")

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

    def _validate_string(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate a string value."""
        if not isinstance(value, str):
            raise StructuredOutputError(f"{path} must be a string")

    def _validate_boolean(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate a boolean value."""
        if not isinstance(value, bool):
            raise StructuredOutputError(f"{path} must be a boolean")

    def _validate_integer(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate an integer value, rejecting booleans."""
        if not isinstance(value, int) or isinstance(value, bool):
            raise StructuredOutputError(f"{path} must be an integer")

    def _validate_number(self, value: Any, schema: dict[str, Any], path: str) -> None:
        """Validate a number value, rejecting booleans."""
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise StructuredOutputError(f"{path} must be a number")

    _TYPE_VALIDATORS: ClassVar[dict[str, Callable[..., None]]] = {
        "object": _validate_object,
        "array": _validate_array,
        "string": _validate_string,
        "boolean": _validate_boolean,
        "integer": _validate_integer,
        "number": _validate_number,
    }
