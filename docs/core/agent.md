# Agent

The `Agent` is the minimal orchestration layer between the `Engine` and the
`LLM` port.

```text
Engine -> Agent -> LLM port -> Ollama adapter
```

The Engine gives the Agent the conversation history prepared by the pipeline.
The Agent sends that history to `LLM.chat()` and relays the streamed model
events back to the Engine.

## Streaming

`Agent.run()` is an asynchronous generator:

```python
async for event in self._llm.chat(messages):
    yield event
```

`yield` passes each event to the Engine immediately instead of waiting for the
whole response. For example, a `TextDelta("Hello")` emitted by the LLM is sent
to the Engine as soon as it arrives. The Engine then turns it into a public
`TokenGenerated` event and publishes it through the event bus.

## Errors

The Agent catches `LLMError` subclasses, such as an unavailable Ollama server
or a missing model, and raises `AgentError` instead. `AgentError` is a core
`SensaiError`, so the Engine can publish it as an `ErrorEvent` without exposing
adapter-specific failures to front-ends.

## Prompts

The agent adds no system message: the Engine prepends it (the active `system`
prompt followed by the user profile), so the model receives exactly one.

`ReActAgent` takes its three prompts as an `AgentPrompts` value
(`core/agent/prompts.py`):

| Field | Prompt name | Used for |
| --- | --- | --- |
| `thought` | `react_thought` | Private thought before acting; `{tools}` is filled in |
| `notes` | `react_notes` | Wraps the thought for the acting call; `{thought}` is filled in |
| `answer` | `react_answer` | Final "answer now" request after tool results |

`app.py` builds it from the active versions in the prompt library;
`AgentPrompts.defaults()` uses the texts shipped with the code (tests, or any
caller without a database). See [Prompt Versioning](prompts.md).

Plan mode and permission prompts belong to later orchestration features.
