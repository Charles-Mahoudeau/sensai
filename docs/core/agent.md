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
| `thought` | `react_thought` | Private thought and its action; `{tools}` is filled in |
| `notes` | `react_notes` | Wraps the turn's previous thoughts for the next thought and the answer; `{thought}` is filled in |
| `answer` | `react_answer` | Final "answer now" request after tool results |

`app.py` builds it from the active versions in the prompt library;
`AgentPrompts.defaults()` uses the texts shipped with the code (tests, or any
caller without a database). See [Prompt Versioning](prompts.md).

## Memory

`ReActAgent` handles memory in two steps around the loop:

- **Before the first thought**, a `MemoryRecall` (`core/agent/memory_recall.py`)
  appends the stored memories to the run's system message, under "What you
  remember about the user". Up to 20 records, all of them are shown; past that,
  the records matching the user's message come first, then the most recent. The
  block is rebuilt every turn and never persisted, so a fact saved in a cleared
  conversation is there in the next one.
- **After the answer**, a `MemoryExtractor` (`core/agent/memory_extraction.py`)
  asks the model, with a JSON schema, for the durable facts the message states
  and the stored subjects it asks to forget. The code then plans one
  `memory_create`, `memory_update` or `memory_delete` per subject, and the agent
  runs them through the tool registry, so they appear as tool calls. A failed
  extraction is logged and skipped.

The recall only runs while `memory_read` is enabled; a planned write only runs
while its tool is enabled: with `--no-tools`, nothing is shown or recorded.
`app.py` passes both when it has a memory repository, with the active versions
of the `memory_extraction` and `memory_recall` prompts (`MemoryPrompts`, next to
`AgentPrompts`): like the ReAct prompts, they are versioned in the library.

Why the system message and not a `memory_read` result: a small model ignored a
tool result it never asked for, but uses the system message, as it does the
user profile. When every stored memory is shown, `memory_read` is no longer
offered: a search could find nothing new, and its empty result read as "nothing
is stored".

The model is never offered the write tools while an extractor is set: pushed
by the chat template to call some tool, it called `memory_delete` on its own.
The extractor guards its writes too:

- the prompt gives examples, so that facts like a home town or a favourite team
  are caught, not only preferences;
- a message made only of questions gives no fact (asked for the facts of "Which
  team do I support?", the model made one up), and no model call at all when
  nothing is stored;
- one call per subject, as the model sometimes repeats a fact;
- a delete targets only a record with exactly the forgotten name, never one the
  same message restates.

Categories are one of `MEMORY_CATEGORIES` (`core/models/memory.py`), in English
whatever the user's language, and a `type` filter ignores case and accents, so
`preference` also finds an older `préférence`.

## Steps

A turn is a few **steps**, then one **answer**:

```text
repeat up to thinking_effort.level times:
    step = thought + action, in JSON under the step schema
    action "answer"  -> stop
    action <tool>    -> the agent runs it, and adds the call and its result
answer = one call without tools, streamed to the user
```

The step schema (`core/agent/step.py`) has one `anyOf` branch per offered tool,
`{"thought", "action": <tool>, "arguments": <its parameters>}`, and one for the
answer, `{"thought", "action": "answer"}`. Constrained by it, the model can't
write a tool call as text or pair a tool with another one's arguments: a step
is always an offered tool or the answer. The model is never given native tools,
so the answer, the only text the user sees as the reply, has nothing to call.

The thoughts are the turn's notes: each step and the answer get the previous
ones, wrapped by `react_notes`. The answer request is the user's message with
the notes appended, or, after tool results, `react_answer` and the notes.

### Portable tool schemas

A tool's parameters are copied into the step schema only as far as every Ollama
version with JSON schemas turns them into a grammar: `type`, `properties`,
`required`, `items` and `enum`. Descriptions and limits such as `minimum` are
dropped, as is a combination of `required` lists ("one of these fields", as in
`memory_read`): they only narrow the values. A tool whose parameters combine
schemas otherwise (`anyOf` of types, `$ref`, a list of types...) accepts any
object in the grammar.

Either way, the arguments are checked against the tool's real parameters before
it runs. Invalid ones run nothing: the error is the call's result, so the next
step can fix them. A server that refuses the step schema before replying gets
the flat one, `{"thought", "action": <enum of names>, "arguments": {}}`, for the
rest of the agent's life.

### Guards

The code, not the prompt, keeps a small model from looping:

- a call repeating an earlier one of the turn ends the steps; calls are compared
  on their **required** arguments, as a small model repeats a search changing
  only its result count;
- a tool failing twice in a turn is left out of the next steps;
- a thought that stops mid-sentence was cut: a double quote the model meant to
  open a quotation closed the JSON string, and the schema forced an action
  before the reasoning concluded. An answer chosen that way is not trusted:
  once per turn, the agent thinks again, the cut thought kept as a note. A call
  chosen that way still runs, as its arguments are concrete. The thought
  prompt also asks for « » or ' ' instead of double quotes;
- once the budget is spent, the agent answers with what it has.

A reply that is not a step (cut off, or a server ignoring the schema) is shown
whole as the thought and ends the steps.

### Streaming

The thought streams: every branch puts `thought` first, and `ThoughtStream`
(`core/agent/thought_stream.py`) decodes that string chunk by chunk, an escape
cut between two chunks (`\u00e9`) waiting for the next one; the action is read
once the reply is complete, and an answer action tags the step as ready. An
empty `ThinkingDelta` first opens the step in the front-end, so its clock runs
while the model reads the prompt.

Plan mode and permission prompts belong to later orchestration features.
