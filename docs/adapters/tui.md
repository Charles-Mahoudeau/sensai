# Terminal UI

The terminal front-end lives in `src/sensai/adapters/tui/` and is built with
[Textual](https://textual.textualize.io/). It is what `uv run sensai` starts:

```bash
uv run sensai --model llama3.2:3b --config config/sensai.toml
```

Like every front-end, it only talks to the core through the `Engine` facade
(`submit()`, `interrupt()`) and its event stream (`subscribe()`). It never
imports the agent, the pipeline, a port or an adapter. See
[Engine and Event Bus](../core/engine.md).

## Files

| File | Role |
| --- | --- |
| `chat_app.py` | `SensaiApp`: layout, input handling, event rendering |
| `widgets.py` | One widget per kind of transcript line |
| `sensai.tcss` | App stylesheet, loaded with `CSS_PATH` |

## Usage

| Action | Effect |
| --- | --- |
| `Enter` | Send the message |
| Empty input | Shows a hint, nothing is sent |
| `/exit`, `/quit`, `ctrl+q` | Quit |
| `esc` | Stop the answer being generated, keeping the partial text |

The prompt is disabled while an answer is generating, because the engine
accepts one submission at a time. The status line shows the model, the current
state and the key hints.

## Wiring

`app.py` builds everything and hands the app a ready `Engine`:

```python
async def _serve(config: Config) -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        engine = build_engine(config, client)
        await SensaiApp(engine, model=config.model).run_async()
```

`run_async()` runs Textual inside the loop started by `asyncio.run()`, so the
engine task, the HTTP client and the UI share one event loop. The HTTP client is
closed when the app exits.

## How events are rendered

In `on_mount()`, the app subscribes to the engine **before** anything can be
submitted, then starts a Textual worker that consumes the event stream for the
app's lifetime. Events from other submissions are ignored.

| Event | Rendering |
| --- | --- |
| `MessageStarted` | Mount an empty `AssistantMessage` |
| `TokenGenerated` | Append the text to it |
| `MessageCompleted` | Finalize the answer (show the message content if nothing was streamed) |
| `ErrorEvent` | Remove the empty answer and show an `ErrorMessage` |
| `Done` | Re-enable the prompt; add "(interrupted)" if `esc` was pressed |

The app only renders: history, error translation and generation are handled by
the core. An error therefore never ends the session; the next message works as
usual.

## Widgets

| Widget | Shows |
| --- | --- |
| `UserMessage` | The user's message |
| `AssistantMessage` | The answer, rendered as Markdown while it streams |
| `ErrorMessage` | An error reported by the engine |
| `HintMessage` | Hints and the "(interrupted)" marker |

`AssistantMessage` streams through `Markdown.get_stream()`, which batches fast
tokens instead of re-rendering the document on each one. Its method is called
`add_fragment()`: `Markdown` already has an `append()` that `MarkdownStream`
calls internally, and overriding it makes the text loop endlessly.

Each widget stores its plain text in `.text`, which the tests use for
assertions.

## Styling

Styles follow the Textual convention:

- each widget has a small `DEFAULT_CSS` with its baseline look;
- `sensai.tcss` holds the app layout and overrides widget defaults.

The stylesheet only uses theme variables (`$accent`, `$primary`, `$error`…), so
the look follows the active theme (`ctrl+p` → "Change theme").

## Tests

`tests/adapters/tui/test_chat_app.py` builds a real
`Engine(Agent(FakeLLM(...)), Pipeline(), EventBus())` and drives the app
headlessly with Textual's `app.run_test()`. No Ollama is needed.

```python
async with app.run_test() as pilot:
    app.query_one("#prompt", Input).value = "Hello"
    await pilot.press("enter")
```

## Adding an event

When the core adds a public event (for example tool calls or thinking), add a
`case` in `SensaiApp._render()` and, if needed, a widget in `widgets.py`.
Unknown events are ignored until then.
