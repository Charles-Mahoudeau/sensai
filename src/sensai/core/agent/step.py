"""The action a ReAct thought ends with: call one tool, or answer.

Each thought is asked for in JSON, under a schema that only allows a valid
action: `{"thought": ..., "action": <tool>, "arguments": {...}}` for each tool,
or `{"thought": ..., "action": "answer"}`. The model can then never write a tool
call as text: it either picks a tool with arguments shaped like its parameters,
or says it can answer.

A tool's parameters are copied into the schema only as far as every Ollama
version with JSON schemas turns them into a grammar: types, properties,
required, items and enums. Other limits, such as a minimum, are dropped and
checked by `check_arguments` instead. A tool whose parameters combine schemas
(`anyOf`, `$ref`...) for more than required fields accepts any object. The
checks ignore those keywords too, so its arguments reach the tool unchecked.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sensai.core.agent.structured import JsonSchemaOutput, StructuredOutputError
from sensai.core.models import ToolCall

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models import ToolSpec

ANSWER = "answer"
"""The action that ends the thoughts: the conversation is enough to answer."""

_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean"})
# Keywords that combine or reference schemas: not every grammar handles them.
_COMBINING = frozenset(
    {
        "$ref",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
        "patternProperties",
        "prefixItems",
        "dependentSchemas",
    }
)
_ANY_OBJECT: dict[str, Any] = {"type": "object"}
# How a finished thought ends; one ending otherwise was cut.
_SENTENCE_ENDS = (".", "!", "?", "…", "»", ")", "]")


@dataclass(frozen=True, slots=True)
class Step:
    """One thought, and the tool it calls, if any.

    Attributes:
        thought: The private reasoning, shown to the user as it is written.
        call: The tool to run next; `None` when the agent can answer.
        cut: Whether the thought stops mid-sentence. A double quote the model
            meant to open a quotation closes the JSON string, and the schema
            then forces an action before the reasoning concluded.
    """

    thought: str
    call: ToolCall | None = None
    cut: bool = False


def step_schema(tools: Sequence[ToolSpec]) -> dict[str, Any]:
    """Build the schema of a step: one branch per tool, plus the answer.

    Every branch starts with `thought`, so the reasoning streams before the
    model commits to an action.
    """
    branches = [
        _branch(
            {"action": {"const": tool.name}, "arguments": portable_arguments(tool)},
        )
        for tool in tools
    ]
    branches.append(_branch({"action": {"const": ANSWER}}))
    return {"anyOf": branches}


def flat_step_schema(tools: Sequence[ToolSpec]) -> dict[str, Any]:
    """Build a step schema without `anyOf` or `const`, for a server refusing them.

    Arguments are any object here: `check_arguments` checks them.
    """
    return {
        "type": "object",
        "properties": {
            "thought": {"type": "string"},
            "action": {"type": "string", "enum": [*(t.name for t in tools), ANSWER]},
            "arguments": {"type": "object"},
        },
        "required": ["thought", "action", "arguments"],
    }


def portable_arguments(tool: ToolSpec) -> dict[str, Any]:
    """Return the part of a tool's parameters that any grammar supports.

    A schema that combines or references others, or that is not an object,
    becomes any object.
    """
    schema = _portable(tool.parameters)
    if schema is None or schema.get("type") != "object":
        return dict(_ANY_OBJECT)
    return {**schema, "additionalProperties": False}


def parse_step(text: str, tools: Sequence[ToolSpec]) -> Step:
    """Read a step written under `step_schema` or `flat_step_schema`.

    A reply that is not a step, such as one cut off by the length limit, is an
    answer whose thought is the raw text: the agent then answers with what it
    has rather than loop on a broken reply.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return Step(text.strip())
    if not isinstance(data, dict):
        return Step(text.strip())
    thought = data.get("thought")
    thought = thought.strip() if isinstance(thought, str) else ""
    cut = bool(thought) and not thought.endswith(_SENTENCE_ENDS)
    action = data.get("action")
    arguments = data.get("arguments")
    if not isinstance(action, str) or action not in {tool.name for tool in tools}:
        return Step(thought, cut=cut)
    if not isinstance(arguments, dict):
        arguments = {}
    return Step(thought, ToolCall(action, arguments, new_call_id()), cut=cut)


def check_arguments(tool: ToolSpec, arguments: Mapping[str, Any]) -> str | None:
    """Check call arguments against the tool's own parameters.

    Returns:
        What is wrong with them, or `None` when they are valid.
    """
    try:
        JsonSchemaOutput(tool.parameters).check(dict(arguments), "arguments")
    except StructuredOutputError as error:
        return str(error)
    return None


def call_key(tool: ToolSpec, call: ToolCall) -> tuple[str, str]:
    """Identify a call by its tool and required arguments.

    Optional arguments, such as a result count, don't make a search new: a
    small model repeats a search changing only those. A tool without required
    arguments is identified by all of them.
    """
    required = tool.parameters.get("required") or ()
    arguments = dict(call.arguments)
    if required:
        arguments = {name: arguments.get(name) for name in required}
    return call.name, json.dumps(arguments, sort_keys=True, default=str)


def new_call_id() -> str:
    """Generate the id of a tool call chosen in a step."""
    return f"call_{uuid.uuid4().hex[:8]}"


def _branch(properties: dict[str, Any]) -> dict[str, Any]:
    """Build one step branch: the thought first, then the given properties."""
    return {
        "type": "object",
        "properties": {"thought": {"type": "string"}, **properties},
        "required": ["thought", *properties],
        "additionalProperties": False,
    }


def _only_requires(branches: Any) -> bool:
    """Tell whether combined schemas only list required fields."""
    return isinstance(branches, list) and all(
        isinstance(branch, Mapping) and branch.keys() <= {"required"}
        for branch in branches
    )


def _portable(schema: Any) -> dict[str, Any] | None:
    """Keep the keywords any grammar supports; `None` if one can't be dropped.

    Descriptions and value limits only narrow the values: dropping them makes
    the grammar looser, not wrong. So does a combination of `required` lists,
    such as "one of these fields". Other combining keywords change the shape,
    so a schema using one can't be copied at all.
    """
    if not isinstance(schema, Mapping):
        return None
    if any(not _only_requires(schema[key]) for key in _COMBINING & schema.keys()):
        return None
    portable: dict[str, Any] = {}
    if "type" in schema:
        type_ = schema["type"]
        if not isinstance(type_, str) or type_ not in _TYPES:
            return None  # "null", or a list of types
        portable["type"] = type_
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not all(
            isinstance(value, str | int | float) for value in enum
        ):
            return None
        portable["enum"] = list(enum)
    if set(schema.get("required") or ()) - set(schema.get("properties") or ()):
        return None  # a required name the grammar can't declare
    if "properties" in schema:
        if not isinstance(schema["properties"], Mapping):
            return None
        properties = {}
        for name, value in schema["properties"].items():
            if (property_schema := _portable(value)) is None:
                return None
            properties[name] = property_schema
        portable["properties"] = properties
        portable["required"] = [
            name for name in schema.get("required") or () if name in properties
        ]
    if "items" in schema:
        if (items := _portable(schema["items"])) is None:
            return None
        portable["items"] = items
    return portable
