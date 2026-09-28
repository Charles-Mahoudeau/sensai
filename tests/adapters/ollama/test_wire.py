"""Tests for the pure translation between core models and Ollama JSON."""

from __future__ import annotations

import json

import pytest

from sensai.adapters.ollama import _wire
from sensai.core.models.llm import (
    ChatDone,
    ChatOptions,
    Message,
    TextDelta,
    ThinkingDelta,
    ToolCallRequest,
    Usage,
)
from sensai.core.models.tools import ToolCall, ToolSpec
from sensai.core.ports import LLMResponseError


def test_plain_messages_are_translated() -> None:
    """System, user and assistant messages keep only role and content."""
    assert _wire.message_to_wire(Message.user("Hi")) == {
        "role": "user",
        "content": "Hi",
    }
    assert _wire.message_to_wire(Message.system("Be brief")) == {
        "role": "system",
        "content": "Be brief",
    }


def test_assistant_message_carries_reasoning_and_tool_calls() -> None:
    """Reasoning goes to `thinking`; tool calls keep their id and arguments."""
    message = Message.assistant(
        tool_calls=(ToolCall("get_weather", {"city": "Paris"}, "call_1"),),
        reasoning_summary="I need the weather",
    )

    assert _wire.message_to_wire(message) == {
        "role": "assistant",
        "content": "",
        "thinking": "I need the weather",
        "tool_calls": [
            {
                "id": "call_1",
                "function": {"name": "get_weather", "arguments": {"city": "Paris"}},
            }
        ],
    }


def test_tool_call_without_id_omits_the_key() -> None:
    """A call that has no id is sent without an `id` field."""
    assert "id" not in _wire.tool_call_to_wire(ToolCall("get_weather"))


def test_tool_message_carries_name_and_call_id() -> None:
    """A tool result is linked to its call by name and id."""
    message = Message.tool("Sunny", tool_name="get_weather", tool_call_id="call_1")

    assert _wire.message_to_wire(message) == {
        "role": "tool",
        "content": "Sunny",
        "tool_name": "get_weather",
        "tool_call_id": "call_1",
    }


def test_tool_spec_hides_requires_confirmation() -> None:
    """The permission flag is for the core and is never sent to the model."""
    spec = ToolSpec("get_weather", "Get the weather", requires_confirmation=True)

    wire = _wire.tool_to_wire(spec)

    assert wire["type"] == "function"
    assert wire["function"]["name"] == "get_weather"
    assert "requires_confirmation" not in json.dumps(wire)


def test_payload_without_tools_or_options_is_minimal() -> None:
    """Only model, messages and `stream` are sent by default."""
    payload = _wire.chat_payload("llama3", [Message.user("Hi")], (), None)

    assert payload == {
        "model": "llama3",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
    }


def test_payload_maps_options_to_ollama_names() -> None:
    """`max_tokens` becomes `num_predict`; schema and thinking are top level."""
    options = ChatOptions(
        temperature=0.2,
        top_p=0.9,
        seed=7,
        num_ctx=4096,
        max_tokens=128,
        response_schema={"type": "object"},
        think=True,
    )

    payload = _wire.chat_payload("m", [Message.user("Hi")], (), options)

    assert payload["options"] == {
        "temperature": 0.2,
        "top_p": 0.9,
        "seed": 7,
        "num_ctx": 4096,
        "num_predict": 128,
    }
    assert payload["format"] == {"type": "object"}
    assert payload["think"] is True


def test_payload_omits_unset_options() -> None:
    """Unset options are left out so the model keeps its defaults."""
    payload = _wire.chat_payload("m", [], (), ChatOptions(seed=1))

    assert payload["options"] == {"seed": 1}
    assert "format" not in payload
    assert "think" not in payload


def test_payload_is_json_serializable() -> None:
    """Frozen mappings from the core models are converted to plain dicts."""
    payload = _wire.chat_payload(
        "m",
        [Message.assistant(tool_calls=(ToolCall("t", {"a": 1}, "c1"),))],
        [ToolSpec("t", "A tool", {"type": "object", "properties": {}})],
        ChatOptions(response_schema={"type": "object"}),
    )

    json.dumps(payload)


def test_decode_chunk_rejects_bad_lines() -> None:
    """Invalid JSON, non-objects and error lines are response errors."""
    for line in ("not json", "[1, 2]", '{"error": "model crashed"}'):
        with pytest.raises(LLMResponseError):
            _wire.decode_chunk(line)


def test_decode_chunk_reports_the_server_error_text() -> None:
    """The server's own message is kept."""
    with pytest.raises(LLMResponseError, match="model crashed"):
        _wire.decode_chunk('{"error": "model crashed"}')


def test_text_thinking_and_done_become_events() -> None:
    """One line can carry thinking and text; `done` adds a closing ChatDone."""
    chunk = {
        "message": {"thinking": "hmm", "content": "Hello"},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 5,
        "eval_count": 2,
    }

    assert _wire.events_from_chunk(chunk) == [
        ThinkingDelta("hmm"),
        TextDelta("Hello"),
        ChatDone(Usage(completion_tokens=2, prompt_tokens=5), "stop"),
    ]


def test_empty_content_produces_no_event() -> None:
    """An empty fragment is not turned into an empty TextDelta."""
    assert _wire.events_from_chunk({"message": {"content": ""}, "done": False}) == []


def test_done_without_counts_gives_zero_usage() -> None:
    """A final line that reports no token counts still yields a ChatDone."""
    assert _wire.events_from_chunk({"done": True}) == [ChatDone(Usage(0, 0), None)]


def test_tool_call_keeps_the_id_from_ollama() -> None:
    """When Ollama identifies a call, its id is used as is."""
    chunk = {
        "message": {
            "tool_calls": [
                {
                    "id": "call_x",
                    "function": {"name": "get_weather", "arguments": {"city": "Paris"}},
                }
            ]
        }
    }

    (event,) = _wire.events_from_chunk(chunk)

    assert event == ToolCallRequest(
        ToolCall("get_weather", {"city": "Paris"}, "call_x")
    )


def test_tool_call_without_id_gets_a_generated_one() -> None:
    """The adapter makes an id, because the core needs one to answer the call."""
    chunk = {"message": {"tool_calls": [{"function": {"name": "t", "arguments": {}}}]}}

    (event,) = _wire.events_from_chunk(chunk, lambda: "call_fixed")

    assert isinstance(event, ToolCallRequest)
    assert event.call.id == "call_fixed"


def test_tool_call_arguments_given_as_json_text_are_parsed() -> None:
    """Some servers send the arguments as a JSON string."""
    chunk = {
        "message": {
            "tool_calls": [{"function": {"name": "t", "arguments": '{"a": 1}'}}]
        }
    }

    (event,) = _wire.events_from_chunk(chunk)

    assert isinstance(event, ToolCallRequest)
    assert dict(event.call.arguments) == {"a": 1}


def test_malformed_tool_calls_are_response_errors() -> None:
    """A tool call without a name, or with unusable arguments, is rejected."""
    bad_calls = [
        {"function": {"arguments": {}}},
        {"function": {"name": "t", "arguments": "not json"}},
        {"function": {"name": "t", "arguments": [1]}},
        "nonsense",
    ]
    for bad in bad_calls:
        with pytest.raises(LLMResponseError):
            _wire.events_from_chunk({"message": {"tool_calls": [bad]}})


def test_error_message_prefers_the_json_error_field() -> None:
    """The text of `{"error": ...}` is used, then the raw body, then the status."""
    assert (
        _wire.error_message(404, b'{"error": "model not found"}') == "model not found"
    )
    assert _wire.error_message(502, b"Bad gateway") == "Bad gateway"
    assert _wire.error_message(500, b"") == "HTTP 500"
