# Core Ports

The ports in `src/sensai/core/ports/` are the interfaces the core needs from the outside world. Each port is a `typing.Protocol` that declares what the core asks for, in core types only. They contain no logic: the real implementations live in `adapters/`, and scripted ones live in `tests/fakes/`.

## Common Principles

Ports follow the rules of `docs/STRUCTURE.md`:

- **The core owns the interface.** Method names describe what the core needs (`search`, `append_message`), never a technology (`execute_sql`, `post_json`).
- **Core types in and out.** Signatures use the models from `core/models/` and the standard library. `httpx`, `sqlite3`, raw Ollama JSON, and similar library types never appear.
- **Minimal.** A method is added when a caller needs it, not because the backend supports it.
- **Errors are part of the contract.** Each port module defines its exceptions next to the Protocol. Adapters translate library exceptions into these, and the core only catches these.
- **Grouped by concern.** One module per concern, re-exported from `core/ports/__init__.py`, so callers write `from sensai.core.ports import LLM`.
- **Checked by shape.** Adapters and fakes do not inherit from the port. The type checker verifies them wherever they are passed as a port, and a `_conforms` function at the bottom of each fake makes it check them in their own file. Their methods must be fully annotated, with the same parameter names and compatible types.

Every new port is delivered with an adapter and a fake in `tests/fakes/`.

## LLM

Module: `core/ports/llm.py`.

### `LLM`

`LLM` streams a chat completion. Its single method, `chat`, takes the conversation, and optionally the tools the model may call and the generation options, and returns an `AsyncIterator[ChatEvent]`.

- `messages` is the whole history to send, oldest first. The model is stateless, so every call carries it. It is a `Sequence`, so callers may pass a list or a tuple.
- `tools` lists the `ToolSpec` objects the model may call in this turn. The default is no tools. `requires_confirmation` is not sent to the model; the tool registry uses it.
- `options` is a `ChatOptions`. `None` keeps the model's defaults.
- `tools` and `options` are keyword-only, so calls stay readable and new options can be added without breaking callers.

The stream yields `TextDelta`, `ThinkingDelta`, and `ToolCallRequest` events in generation order, and ends with exactly one `ChatDone` that carries the token usage. The method is declared with a plain `def`: implementations are `async def` generators using `yield`, and an `async def` in the Protocol would describe a coroutine that no generator matches.

Errors are raised while iterating the stream, not when `chat` is called.

### Errors

- `LLMError` is the base class of every error below;
- `LLMUnavailableError`: the model server cannot be reached;
- `ModelNotFoundError`: the requested model does not exist on the server;
- `LLMResponseError`: the server answered with something that cannot be understood.

## Retrieval

Module: `core/ports/retrieval.py`. `Embedder` and `VectorStore` share a module because they only make sense together.

### `Vector`

`Vector` is a `Sequence[float]`. It keeps the core independent of numeric libraries. Adapters may use faster representations internally.

### `Embedder`

`Embedder` turns texts into vectors. `embed` takes a batch of texts and returns one vector per text, in the same order, all with the same length. It is a plain `async def` because it returns one result and does not stream.

### `VectorStore`

`VectorStore` stores chunks with their vectors and finds the most similar ones.

- `add(chunks, vectors)` inserts chunks and replaces any chunk that has the same id, so ingesting twice does not duplicate. It raises `ValueError` when the two sequences have different lengths.
- `search(vector, k, *, where=None)` returns at most `k` `ScoredChunk` objects, most similar first. A higher score always means more similar. `where` is a metadata filter: a chunk is considered only if its metadata contains every given key with an equal value.
- `delete(document_id)` removes every chunk of a document and does nothing if the document is unknown. Re-ingesting a changed document is a `delete` followed by an `add`.

The filter only supports exact matches. Range filters, such as dates, would require a change of the port.

### Errors

- `RetrievalError` is the base class of every error below;
- `EmbedderUnavailableError`: the embedding server cannot be reached;
- `EmbeddingModelNotFoundError`: the embedding model does not exist;
- `VectorStoreError`: the store failed to read or write its data.

## Memory

Module: `core/ports/memory.py`. Both stores are asynchronous. The SQLite adapter runs its blocking calls in a worker thread, so the async core never blocks.

### `SessionStore`

`SessionStore` saves conversations and the persistent user profile.

- `create_session`, `get_session`, and `list_sessions` manage `Session` objects. `list_sessions` returns the most recently updated first and accepts a `limit`.
- `append_message` adds a `Message` at the end of a session and refreshes the session's update time. `get_messages` returns the messages of a session, oldest first, ready to be sent to `LLM.chat`.
- `delete_session` removes a session with its messages.
- `get_profile` returns the profile as key/value pairs, empty when nothing is set. `set_profile_value` creates or replaces an entry, and `delete_profile_value` removes one and does nothing if the key is unknown.

### `MemoryStore`

`MemoryStore` holds the long-term memory that the agent drives through CRUD tool calls.

- `create` makes a `MemoryRecord` from a name, a type, and an optional description. The pair name and type must be unique.
- `get` returns one record by identifier.
- `find` searches records, most recently updated first. `type` restricts the type, and `query` matches text in the name or the description, ignoring case. Both `None` returns everything.
- `update` changes some fields of a record. A `None` argument keeps the current value, so an empty string is used to clear the description.
- `delete` removes a record.

Unlike `VectorStore.delete`, deleting or updating an unknown identifier raises an error. The agent chooses the identifier, and it needs to be told when it is wrong.

Soft deletes and an audit trail are adapter concerns and do not change the port.

### Errors

- `StorageError` is the base class of every error below;
- `SessionNotFoundError`: no session has the given identifier;
- `MemoryNotFoundError`: no memory record has the given identifier;
- `DuplicateMemoryError`: a record with the same name and type already exists.

## Fakes

`tests/fakes/` contains one scripted or in-memory implementation per port:

- `FakeLLM` plays back one scripted turn per `chat` call, records the messages, tools, and options it received, and can raise an exception at any point of the stream. It adds the closing `ChatDone` when a turn does not end with one.
- `FakeEmbedder` returns predefined vectors and fails on an unknown text.
- `InMemoryVectorStore` computes cosine similarity by brute force and follows the same rules as the port.
- `InMemorySessionStore` and `InMemoryMemoryStore` keep their data in dictionaries. Their clock can be injected, and by default it advances one second per call, so ordering is deterministic in tests.

## Organization

Docstrings in the Python files describe the contract of each method: what it takes, returns, and raises. Design decisions and detailed explanations are kept in this document so that the port modules remain readable and free of inline comments.
