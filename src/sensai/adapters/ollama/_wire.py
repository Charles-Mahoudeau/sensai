"""Translation between core models and the Ollama wire format."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from sensai.core.models.llm import (
    ChatDone,
    TextDelta,
    ThinkingDelta,
    ToolCallRequest,
    Usage,
)
from sensai.core.models.tools import ToolCall
from sensai.core.ports import LLMResponseError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sensai.core.models.llm import ChatEvent, ChatOptions, Message
    from sensai.core.models.tools import ToolSpec


def new_call_id() -> str:
    """Generate an id for a tool call that Ollama did not identify."""
    return f"call_{uuid.uuid4().hex[:8]}"


def error_message(status_code: int, body: bytes) -> str:
    """Extract the error text of a failed HTTP response."""
    text = body.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        return data["error"]
    return text[:200] or f"HTTP {status_code}"


def tool_call_to_wire(call: ToolCall) -> dict[str, Any]:
    """Convert a tool call to the Ollama format."""
    wire: dict[str, Any] = {
        "function": {"name": call.name, "arguments": dict(call.arguments)}
    }
    if call.id is not None:
        wire["id"] = call.id
    return wire


def message_to_wire(message: Message) -> dict[str, Any]:
    """Convert a chat message to the Ollama format."""
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.reasoning_summary:
        wire["thinking"] = message.reasoning_summary
    if message.tool_calls:
        wire["tool_calls"] = [tool_call_to_wire(call) for call in message.tool_calls]
    if message.role == "tool":
        wire["tool_name"] = message.tool_name
        wire["tool_call_id"] = message.tool_call_id
    return wire


def tool_to_wire(spec: ToolSpec) -> dict[str, Any]:
    """Convert a tool specification to the Ollama format.

    `requires_confirmation` is for the core's permission layer and is not sent.
    """
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.parameters),
        },
    }


def chat_payload(
    model: str,
    messages: Sequence[Message],
    tools: Sequence[ToolSpec],
    options: ChatOptions | None,
) -> dict[str, Any]:
    """Build the JSON body of a streaming `/api/chat` request."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [message_to_wire(message) for message in messages],
        "stream": True,
    }
    if tools:
        payload["tools"] = [tool_to_wire(spec) for spec in tools]
    if options is None:
        return payload

    sampling = {
        "temperature": options.temperature,
        "top_p": options.top_p,
        "seed": options.seed,
        "num_ctx": options.num_ctx,
        "num_predict": options.max_tokens,
    }
    sampling = {key: value for key, value in sampling.items() if value is not None}
    if sampling:
        payload["options"] = sampling
    if options.response_schema is not None:
        payload["format"] = dict(options.response_schema)
    if options.think is not None:
        payload["think"] = options.think
    return payload


def decode_chunk(line: str) -> dict[str, Any]:
    """Parse one line of the chat stream.

    Raises:
        LLMResponseError: The line is not a JSON object, or carries an error.
    """
    try:
        chunk = json.loads(line)
    except ValueError as e:
        raise LLMResponseError(
            f"invalid JSON in the Ollama stream: {line[:100]!r}"
        ) from e
    if not isinstance(chunk, dict):
        raise LLMResponseError(f"unexpected line in the Ollama stream: {line[:100]!r}")
    if "error" in chunk:
        raise LLMResponseError(str(chunk["error"]))
    return chunk


def _tool_call_from_wire(raw: Any, new_id: Callable[[], str]) -> ToolCall:
    function = raw.get("function") if isinstance(raw, dict) else None
    if not isinstance(function, dict) or not function.get("name"):
        raise LLMResponseError(f"malformed tool call from Ollama: {raw!r}")
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError as e:
            raise LLMResponseError(
                f"tool call arguments are not JSON: {arguments!r}"
            ) from e
    if not isinstance(arguments, dict):
        raise LLMResponseError(f"tool call arguments are not an object: {arguments!r}")
    return ToolCall(function["name"], arguments, raw.get("id") or new_id())


def events_from_chunk(
    chunk: Mapping[str, Any], new_id: Callable[[], str] = new_call_id
) -> list[ChatEvent]:
    """Convert one decoded stream line to core events.

    A line that has `done: true` produces a final `ChatDone`.

    Raises:
        LLMResponseError: A tool call in the line is malformed.
    """
    events: list[ChatEvent] = []
    message = chunk.get("message") or {}
    if thinking := message.get("thinking"):
        events.append(ThinkingDelta(thinking))
    if content := message.get("content"):
        events.append(TextDelta(content))
    events.extend(
        ToolCallRequest(_tool_call_from_wire(raw, new_id))
        for raw in message.get("tool_calls") or ()
    )
    if chunk.get("done"):
        usage = Usage(
            completion_tokens=chunk.get("eval_count") or 0,
            prompt_tokens=chunk.get("prompt_eval_count") or 0,
        )
        events.append(ChatDone(usage, chunk.get("done_reason")))
    return events
