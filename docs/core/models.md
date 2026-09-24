# Core Models

The models in `src/sensai/core/models/` are immutable dataclasses used to pass data between ports and core components. They perform no network access, disk writes, or infrastructure-library operations.

## Common Principles

The models use `@dataclass(frozen=True, slots=True)` in order to:

- prevent accidental changes after construction;
- reduce their memory footprint;
- represent values that can be passed between components;
- centralize simple validation in `__post_init__`.

Mappings received by the models are copied and exposed through `MappingProxyType`. This makes the outer mapping structure immutable.

## Chat

### `Role`

`Role` limits message roles to `system`, `user`, `assistant`, and `tool`.

- `system` contains initial instructions, the persona, or global context;
- `user` contains the user's request;
- `assistant` contains the model's response and may carry tool calls;
- `tool` contains the result of a tool call.

### `Message`

`Message` represents one entry in the conversation history. `tool_call_id` is required for a `tool` message so that the result can be associated with the corresponding call. `tool_name` is also reserved for `tool` messages.

An `assistant` message may contain multiple `ToolCall` objects and a reasoning summary exposed through `reasoning_summary`. The `system`, `user`, `assistant`, and `tool` methods are factories for constructing common message forms.

### `ChatOptions`

`ChatOptions` contains optional generation parameters: temperature, `top_p`, seed, context size, token limit, response schema, and model thinking mode. A value of `None` means that the model's default configuration is used.

### `Usage`

`Usage` contains prompt and completion token counts. The counters cannot be negative, and `total_tokens` exposes their sum.

### Streaming Events

- `TextDelta` carries a fragment of generated text;
- `ThinkingDelta` carries a fragment of model reasoning exposed by the model;
- `ToolCallRequest` carries a tool call requested during generation;
- `ChatDone` signals the end of generation and contains usage information and an optional reason;
- `ChatEvent` is the union of these events.

## Tools

### `ToolCall`

`ToolCall` represents a normalized tool invocation with its name, arguments, and an optional identifier supplied by the model.

### `ToolSpec`

`ToolSpec` describes an available tool: its name, description, parameter schema, and whether human confirmation is required before execution.

### `ToolResult`

`ToolResult` represents the output of an invocation. `call_id` associates the result with the exact call, and `is_error` indicates that an error should be returned to the model rather than raised by the data model. The `error` factory directly creates an error result.

Checking tool existence, permissions, and arguments belongs to the registry and the core tool components, not to the models.

## Retrieval

### `Document`

`Document` represents loaded text before it is split into chunks. It has an identity, its text, a source, and metadata.

### `Chunk`

`Chunk` is a portion of a document used by the retrieval pipeline. `document_id` links the chunk to its source document, and `index` indicates its position in that document. Metadata may contain string, numeric, or boolean values.

### `ScoredChunk`

`ScoredChunk` associates a `Chunk` with its relevance score calculated by retrieval or reranking.

### `WebSearchResult`

`WebSearchResult` represents a result returned by a web search, including its title, URL, and snippet. Full content is not stored in this model in order to keep the result lightweight; any later loading belongs to the web adapter.

## Memory

### `Session`

`Session` represents a saved conversation. It has an identifier, the model it talks to, an optional title, and creation and update timestamps. Its messages are not stored in the model: they are loaded separately through the session store as `Message` objects, so that listing sessions stays lightweight.

### `MemoryRecord`

`MemoryRecord` is a long-term memory entry that the agent can create, read, update, and delete. It has an identifier, a `name`, a `type` (for example `person`, `project`, or `concept`), an optional free-text description, and creation and update timestamps. The pair `name` and `type` identifies a record; the store rejects duplicates, not the model.

Timestamps are `datetime` values, expected to be timezone-aware (UTC). The models only check that the fields identifying them are not empty.

## Organization

Docstrings in the Python files describe only the public API required by the code and quality tools. Design decisions and detailed explanations are kept in this document so that the model modules remain readable and free of inline comments.
