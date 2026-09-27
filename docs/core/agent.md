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

The current Agent deliberately has no tool calls, permissions, ReAct loop, or
planning logic. Those behaviors belong to later orchestration features.
