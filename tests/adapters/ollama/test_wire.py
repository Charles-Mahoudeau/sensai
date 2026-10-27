"""Tests for the pure translation between core models and Ollama JSON."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from sensai.adapters.ollama import _wire
from sensai.core.models.llm import (
    ChatDone,
    ChatOptions,
    LoadedModel,
    Message,
    TextDelta,
    ThinkingDelta,
    Timings,
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
    """Only model, messages, `stream` and `think=False` are sent by default."""
    payload = _wire.chat_payload("llama3", [Message.user("Hi")], (), None)

    assert payload == {
        "model": "llama3",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
        "think": False,
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
    assert payload["think"] is False


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


def test_done_durations_become_timings() -> None:
    """Ollama durations, in nanoseconds, are read into the ChatDone timings."""
    chunk = {
        "done": True,
        "total_duration": 3_000_000_000,
        "load_duration": 500_000,
        "prompt_eval_duration": 250_000_000,
        "eval_duration": 2_000_000_000,
    }

    [done] = _wire.events_from_chunk(chunk)

    assert isinstance(done, ChatDone)
    assert done.timings == Timings(
        total=timedelta(seconds=3),
        load=timedelta(microseconds=500),
        prompt_eval=timedelta(milliseconds=250),
        eval=timedelta(seconds=2),
    )


def test_missing_duration_is_read_as_zero() -> None:
    """A final line with only some durations still gives timings."""
    [done] = _wire.events_from_chunk({"done": True, "eval_duration": 1_000_000_000})

    assert isinstance(done, ChatDone)
    assert done.timings is not None
    assert done.timings.eval == timedelta(seconds=1)
    assert done.timings.total == timedelta(0)


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


def test_missing_sizes_and_context_are_defaulted() -> None:
    """Sizes default to zero and an unreported context length to None."""
    assert _wire.loaded_models_from_body({"models": [{"name": "m"}]}) == [
        LoadedModel(name="m", size_bytes=0, vram_bytes=0)
    ]


def test_malformed_api_ps_bodies_are_response_errors() -> None:
    """A wrong shape anywhere in `/api/ps` is reported, not ignored."""
    bad_bodies = [
        [],
        {},
        {"models": None},
        {"models": ["m"]},
        {"models": [{"size": 1}]},
        {"models": [{"name": "m", "size": "big"}]},
        {"models": [{"name": "m", "size": -1}]},
    ]
    for body in bad_bodies:
        with pytest.raises(LLMResponseError):
            _wire.loaded_models_from_body(body)


def test_keep_alive_is_sent_only_when_set() -> None:
    """A set keep_alive is added to the chat payload; None leaves Ollama's default."""
    with_it = _wire.chat_payload("m", [], (), None, keep_alive="30m")
    without = _wire.chat_payload("m", [], (), None)

    assert with_it["keep_alive"] == "30m"
    assert "keep_alive" not in without


def test_load_payload_has_no_prompt() -> None:
    """Loading a model is a generate request without a prompt."""
    assert _wire.load_payload("m", -1) == {
        "model": "m",
        "stream": False,
        "keep_alive": -1,
    }
    assert _wire.load_payload("m", None) == {"model": "m", "stream": False}


def test_max_context_is_read_under_the_architecture() -> None:
    """Ollama files the trained window as `<architecture>.context_length`."""
    body = {
        "model_info": {
            "general.architecture": "llama",
            "llama.context_length": 131_072,
        }
    }

    assert _wire.max_context_from_show(body) == 131_072


def test_missing_or_odd_max_context_is_unknown() -> None:
    """No model info, another architecture's key or a bad value give None."""
    bodies = [
        {},
        {"model_info": None},
        {"model_info": {"general.architecture": "llama"}},
        {"model_info": {"general.architecture": "qwen", "llama.context_length": 9}},
        {"model_info": {"general.architecture": "llama", "llama.context_length": 0}},
        {"model_info": {"general.architecture": "llama", "llama.context_length": "x"}},
    ]
    for body in bodies:
        assert _wire.max_context_from_show(body) is None

    with pytest.raises(LLMResponseError):
        _wire.max_context_from_show([])
