"""Translation between core models and the Ollama wire format."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from sensai.core.models.llm import (
    ChatDone,
    LoadedModel,
    TextDelta,
    ThinkingDelta,
    Timings,
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
    *,
    keep_alive: str | int | None = None,
) -> dict[str, Any]:
    """Build the JSON body of a streaming `/api/chat` request.

    `keep_alive` is how long Ollama keeps the model loaded afterwards; Ollama's
    default applies when it is `None`.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [message_to_wire(message) for message in messages],
        "stream": True,
        "think": False,
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
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


REPLY_PREVIEW = 200
"""Most characters of a reply shown in its log summary."""


def request_summary(
    model: str,
    messages: Sequence[Message],
    tools: Sequence[ToolSpec],
    options: ChatOptions | None,
) -> str:
    """One log line for a chat request: model, size and what it may answer.

    For example `→ llama3 · 3 messages · step(web_search, answer)`.
    """
    count = len(messages)
    parts = [f"→ {model}", f"{count} message{'' if count == 1 else 's'}"]
    if tools:
        parts.append("tools: " + ", ".join(spec.name for spec in tools))
    if options is not None and options.response_schema is not None:
        parts.append(_schema_summary(options.response_schema))
    return " · ".join(parts)


def _schema_summary(schema: Mapping[str, Any]) -> str:
    """Name the actions of a step schema, or the fields of any other schema."""
    branches = schema.get("anyOf") or []
    actions = [
        branch.get("properties", {}).get("action", {}).get("const")
        for branch in branches
    ]
    if actions and all(isinstance(action, str) for action in actions):
        return f"step({', '.join(actions)})"
    enum = schema.get("properties", {}).get("action", {}).get("enum")
    if isinstance(enum, list):
        return f"step({', '.join(map(str, enum))})"
    return f"schema({', '.join(schema.get('properties', {}))})"


def reply_summary(text: str, calls: Sequence[ToolCall], done: ChatDone) -> str:
    """One log line for a reply: duration, tokens, why it stopped, a preview.

    For example `← 2.3 s · 1036 in / 69 out · stop · {"thought": "…"}`.
    """
    parts: list[str] = []
    if done.timings is not None:
        parts.append(f"{done.timings.total.total_seconds():.1f} s")
    usage = done.usage
    parts.append(f"{usage.prompt_tokens} in / {usage.completion_tokens} out")
    if done.done_reason:
        parts.append(done.done_reason)
    if calls:
        parts.append("calls: " + ", ".join(call.name for call in calls))
    if text.strip():
        parts.append(_preview(text))
    return "← " + " · ".join(parts)


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= REPLY_PREVIEW:
        return flat
    return flat[: REPLY_PREVIEW - 1] + "…"


def load_payload(model: str, keep_alive: str | int | None) -> dict[str, Any]:
    """Build the JSON body of a `/api/generate` request that only loads a model.

    Without a prompt, Ollama loads the model into memory and answers at once.
    """
    payload: dict[str, Any] = {"model": model, "stream": False}
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
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
        events.append(
            ChatDone(
                _usage_from_chunk(chunk),
                chunk.get("done_reason"),
                _timings_from_chunk(chunk),
            )
        )
    return events


def _usage_from_chunk(chunk: Mapping[str, Any]) -> Usage:
    """Read the token counts of a final stream line; missing counts are zero."""
    return Usage(
        completion_tokens=chunk.get("eval_count") or 0,
        prompt_tokens=chunk.get("prompt_eval_count") or 0,
    )


_DURATION_KEYS = (
    "total_duration",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
)


def _timings_from_chunk(chunk: Mapping[str, Any]) -> Timings | None:
    """Read the durations of a final stream line, which Ollama gives in ns.

    Returns `None` when the line reports no duration at all; a single missing
    duration is read as zero.
    """
    if not any(key in chunk for key in _DURATION_KEYS):
        return None
    total, load, prompt_eval, eval_ = (
        timedelta(microseconds=(chunk.get(key) or 0) / 1000) for key in _DURATION_KEYS
    )
    return Timings(total=total, load=load, prompt_eval=prompt_eval, eval=eval_)


def loaded_models_from_body(body: Any) -> list[LoadedModel]:
    """Read the models listed by `/api/ps`.

    Raises:
        LLMResponseError: The body does not have the expected shape.
    """
    models = body.get("models") if isinstance(body, dict) else None
    if not isinstance(models, list):
        raise LLMResponseError(f"unexpected /api/ps response from Ollama: {body!r}")
    return [_loaded_model_from_wire(raw) for raw in models]


def _loaded_model_from_wire(raw: Any) -> LoadedModel:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        raise LLMResponseError(f"malformed model in /api/ps: {raw!r}")
    context_length = raw.get("context_length")
    try:
        return LoadedModel(
            name=raw["name"],
            size_bytes=int(raw.get("size") or 0),
            vram_bytes=int(raw.get("size_vram") or 0),
            context_length=None if context_length is None else int(context_length),
        )
    except (TypeError, ValueError) as e:
        raise LLMResponseError(f"malformed model in /api/ps: {raw!r}") from e


def max_context_from_show(body: Any) -> int | None:
    """Read the trained context window from a `/api/show` response.

    Ollama files it under the model's architecture, e.g. `llama.context_length`.
    Returns `None` when the response does not give it.

    Raises:
        LLMResponseError: The body is not a JSON object.
    """
    if not isinstance(body, dict):
        raise LLMResponseError(f"unexpected /api/show response from Ollama: {body!r}")
    info = body.get("model_info")
    if not isinstance(info, dict):
        return None
    value = info.get(f"{info.get('general.architecture')}.context_length")
    # bool is an int in Python, but never a context length
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value
