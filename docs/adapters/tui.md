# Terminal UI

The terminal front-end lives in `src/sensai/adapters/tui/` and is built with
[Textual](https://textual.textualize.io/). It is what `uv run sensai` starts:

```bash
uv run sensai --model llama3.2:3b --config config/sensai.toml
```

Like every front-end, it only talks to the core through the `Engine` facade
(`submit()`, `interrupt()`, `tools()`, `mcp_servers()`…) and its event stream
(`subscribe()`). It never
imports the agent, the pipeline, a port or an adapter. See
[Engine and Event Bus](../core/engine.md).

## Files

| File | Role |
| --- | --- |
| `chat_app.py` | `SensaiApp`: layout, input handling, event rendering; the `CommandContext` of commands |
| `commands/registry.py` | `CommandSpec`, `CommandRegistry` (completion, dispatch), `CommandContext`, `CommandHighlighter` |
| `commands/builtin/` | One module per built-in command, and `default_registry()` |
| `panels/` | `Panel` and the panels commands open in place of the prompt (`McpPanel`, `ToolsPanel`) |
| `widgets/` | One module per widget: the transcript lines, the prompt and its command menu |
| `log_buffer.py` | `LogBuffer`: a logging handler keeping the latest records for `/logs`, and telling listeners of new ones |
| `log_format.py` | `format_record()`: a record as one colored line (time, level, category, message) |
| `companion.py` | `Companion`: the animated face drawn in the prompt border, and its `Mood` frames |
| `sensai.tcss` | App stylesheet, loaded with `CSS_PATH` |

## Usage

| Action | Effect |
| --- | --- |
| `Enter` | Send the message |
| Empty input | Shows a hint, nothing is sent |
| `/exit`, `/quit`, `ctrl+q` | Quit |
| `/clear` | Clear the conversation and start a new session |
| `/effort <level>` | Set the thinking effort (`/effort` alone shows it) |
| `/mcp` | List the MCP servers and whether they connected |
| `/tools` | List the tools, enable or disable them |
| `/logs` | Show this session's log records, live and colored |
| `esc` | Stop the answer being generated, keeping the partial text |
| `ctrl+t` | Expand every reasoning group, or collapse them if all are expanded |
| Click a reasoning header | Expand or collapse that group |

The prompt is disabled while an answer is generating, because the engine
accepts one submission at a time. The status line shows the model, the current
state and the key hints.

## Commands

A line starting with `/` is a command and is never sent to the model. Commands
follow the same pattern as tools (`core/tools/registry.py`): a `CommandSpec`
(name, description, arguments, aliases) and an async handler are registered in a
`CommandRegistry`. The app only calls `registry.run(text, self)`; it has no
per-command code.

The built-in commands:

| Command | Effect |
| --- | --- |
| `/clear` | Awaits the `on_clear` hook (which saves the session and starts a new one), calls `engine.clear()` and empties the transcript |
| `/effort <level>` | Sets `engine.thinking_effort` to `none`, `low`, `medium`, `high` or `ultra`; a bare `/effort` shows the current one |
| `/mcp` | Opens `McpPanel` with `engine.mcp_servers()` |
| `/tools` | Opens `ToolsPanel`, which lists `engine.tools()` and toggles them |
| `/logs` | Opens `LogsPanel` on the `LogBuffer` wired in `app.py`; without one, shows a hint |
| `/exit` | Quits; `/quit` is a hidden alias |

An unknown command shows an "Unknown command" hint.

### Panels

A command that needs more than a hint opens a `Panel` with
`context.open_panel(panel)`. The app hides the prompt and its menu, mounts the
panel in their place (the transcript stays visible) and calls
`panel.focus_first()`. `esc` posts `Panel.Closed`; the app removes the panel and
gives the focus back to the prompt. Opening a panel closes any other one.

`McpPanel` shows one row per configured server: `● github  connected  42 tools`,
or `✗ notion  failed: <reason>`, each with its URL.

Panels keep their title (with the counts) in the top border and their key
hints in the bottom one, so the content keeps the room in a small window.

`LogsPanel` shows the records kept by the `LogBuffer` (the last 1,000, from
INFO), then each new one **as it is logged**, while the panel is open:

```text
21:35:41  WARN   app        GITHUB_TOKEN not set, skipping the GitHub MCP server
21:35:42  INFO   ollama     → qwen2.5:7b · 3 messages · step(web_search, run_python, answer)
21:35:44  INFO   ollama     ← 2.3 s · 1036 in / 69 out · stop · {"thought": "…"}
```

The time is dimmed, the level colored (WARN yellow, ERROR red, DEBUG dim) and
the category too: the logger name without `sensai.`, `adapters.` and `core.`,
cut at its first dot (`sensai.adapters.ollama.chat` → `ollama`). The panel
subscribes to the buffer when mounted and unsubscribes when removed; records
logged from worker threads reach it through `post_message`, which is
thread-safe.

| Key | Effect |
| --- | --- |
| Typing | Show only the records whose message or logger name contains the text |
| `ctrl+l` | Cycle the lowest level shown: DEBUG, INFO, WARNING, ERROR (INFO first) |
| `esc` | Close the panel |

`ToolsPanel` shows `Tools · n/m enabled`, a filter with Enable/Disable all
buttons on the same line, then the tools grouped by source (`builtin`, then one group per MCP server, each
header counting its enabled tools). The list takes the height the panel has
left (`height: 1fr`, at most 20 rows) and scrolls to keep the highlight in
view. Each tool takes one line: its description is cut with `…` at the
panel's edge (`text-wrap: nowrap; text-overflow: ellipsis`), so it uses the
whole width of the terminal. MCP tools are shown without their
`<server>__` prefix. The filter keeps the focus:

| Key | Effect |
| --- | --- |
| Typing | Narrow the list to the tools whose name or description contains the text |
| `↑` / `↓` | Move the highlight, skipping the group headers |
| `space`, `Enter`, click | Enable or disable the highlighted tool |
| `ctrl+a` / `ctrl+d` | Enable / disable every tool shown (all of them when not filtered; the buttons read "Enable shown" / "Disable shown" while filtering) |
| `esc` | Close the panel |

Changes apply from the next message, and only for this run: every tool is
enabled again at the next start.

While typing, a known command name is colored with the theme accent
(`CommandHighlighter`), and `CommandMenu` lists the completions above the
prompt: the matching commands, then, after a command and a space, its
arguments. While the menu is shown, `PromptInput` changes these keys:

| Key | Effect |
| --- | --- |
| `↑` / `↓` | Move the highlight |
| `tab` | Insert the highlighted completion |
| `Enter` | Insert it and run it, unless the text is already complete; a command that takes an argument is only inserted, to pick the argument next |
| `esc` | Close the menu (it does not stop generation) |

When the menu is hidden, these keys work as usual.

### Adding a command

1. Create `commands/builtin/<name>.py` with a handler and a `register_self()`:

   ```python
   def register_self(registry: CommandRegistry) -> None:
       registry.register(CommandSpec("/hello", "Say hello"), _hello)


   async def _hello(context: CommandContext, argument: str) -> None:
       await context.show_hint(f"Hello {argument or 'you'}")
   ```

2. Call it in `default_registry()` (`commands/builtin/__init__.py`). The order
   there is the order of the menu.

The handler receives the argument string (stripped, empty if none) and a
`CommandContext`, the small surface of the front-end a command may use:
`engine`, `show_hint()`, `clear_transcript()`, `refresh_status()`,
`open_panel()` and `exit()`.
`SensaiApp` implements it. A command that needs something from outside the TUI
gets it as a `register_self()` argument, wired in `app.py`, the way `/clear`
gets its `on_clear` hook. If a command needs a new UI action, add it to
`CommandContext` and `SensaiApp`.

## Wiring

`app.py` builds everything and hands the app a ready `Engine`:

```python
recorder = SessionRecorder(
    session_repo, engine, model=config.model, session_id=session.id, saved=len(history)
)
commands = default_registry(on_clear=recorder.start_new)
await SensaiApp(engine, model=config.model, commands=commands).run_async()
await recorder.save()
```

`run_async()` runs Textual inside the loop started by `asyncio.run()`, so the
engine task, the HTTP client and the UI share one event loop. The HTTP client is
closed when the app exits. `app.py` also attaches a `LogBuffer` to the root
logger and passes it as `default_registry(log_buffer=...)`, then detaches it
when the app exits. The `on_clear` hook and the final `save()` keep
the stored sessions in step with `/clear` (see
[Session recording](../core/engine.md#session-recording)).

## How events are rendered

In `on_mount()`, the app subscribes to the engine **before** anything can be
submitted, then starts a Textual worker that consumes the event stream for the
app's lifetime. Events from other submissions are ignored.

| Event | Rendering |
| --- | --- |
| `MessageStarted` | Mount an empty `AssistantMessage` |
| `TokenGenerated` | Append the text to it |
| `MessageCompleted` | Finalize the answer (show the message content if nothing was streamed) |
| `ThinkingGenerated` | Stream into a `ThoughtStep` inside the turn's `ReasoningGroup`; `ready` tags the step |
| `ToolRunStarted` / `ToolRunFinished` | Add a `ToolCallLine` to the same group, then fill in its result; mount an `ArtifactView` per attached file |
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
| `ReasoningGroup` | One turn's thoughts and tool calls, collapsible |
| `ThoughtStep` | One think/act cycle inside a group |
| `ToolCallLine` | One tool call, inside a group |
| `ArtifactView` | A file a tool produced: the image inline, then its path |
| `ErrorMessage` | An error reported by the engine |
| `HintMessage` | Hints, command feedback and the "(interrupted)" marker |
| `PromptInput` | The prompt; highlights commands and drives the menu |
| `CommandMenu` | The completions of the command being typed |

`AssistantMessage` streams through `Markdown.get_stream()`, which batches fast
tokens instead of re-rendering the document on each one. Its method is called
`add_fragment()`: `Markdown` already has an `append()` that `MarkdownStream`
calls internally, and overriding it makes the text loop endlessly.

Each widget stores its plain text in `.text`, which the tests use for
assertions.

## Reasoning display

A ReAct turn can think several times. Instead of one long wall of italic text,
the turn gets one `ReasoningGroup`:

- **While the agent works**, the header shows a spinner, the current step and a
  clock. The step being generated shows only its last 3 lines; finished steps
  shrink to a one-line summary. A thought that concluded the answer can be
  written is tagged "ready to answer" (the `ready` flag of `ThinkingGenerated`).
- **When the answer starts**, the group collapses to a line such as
  `▸ Reasoned · 2 steps · 1 tool · 8s`.
- **Expanded** (click or `ctrl+t`), every step shows its whole thought rendered
  as Markdown, with the tool calls between them.

What is visible is decided by CSS classes on the group (`-live`, `-full`,
`-collapsed`) and on each step (`-streaming`, `-done`); see `sensai.tcss`.
A text fragment arriving before a later tool call closes the group, so that
tool call opens a new one.

## Inline artifacts

A tool can return files with its result (`ToolResult.attachments`), such as
the plots `run_python` saves (see [Code Sandbox](../core/sandbox.md)). Each
file gets an `ArtifactView` in the transcript, **outside** the reasoning group,
so it stays visible when the group collapses:

```text
› Plot sin(x) on [0, 2π]
▸ Reasoned · 2 steps · 1 tool · 6s
  [the plot]
  ↳ artifacts/2026-10-29/142310-a1b2c3/sine.png
Here is the plot of sin(x).
```

Images are drawn with [textual-image](https://github.com/lnqs/textual-image),
which picks the best protocol the terminal supports (Kitty, Sixel) and falls
back to colored half-blocks. An image that can't be read shows a short message
instead. Other files only show their path. Later thoughts of the same turn still
go into the group above the image.

## Companion

A small kaomoji face lives in the top-right corner of the prompt border (its
right-aligned `border_title`). It takes no extra row and reacts to the turn:

| Mood | Face | When |
| --- | --- | --- |
| idle | `(•ᴗ•)`, blinking | Nothing is happening |
| typing | `(•ᴗ<)` | The prompt holds text |
| thinking | `...(•_•)` | Submitted, `ThinkingGenerated`, or after the last tool returns |
| tool | `◐(•ᴗ•)` | `ToolRunStarted` |
| answering | `(•o•)` | `TokenGenerated` |
| error | `(×_×)` | `ErrorEvent`, then for 3s after `Done` |
| interrupted | `!(°□°)` | `esc`, then for 2s after `Done` |
| happy | `♪(^ᴗ^)` | For 2s after a turn that ended well |
| asleep | `zZz(-_-)` | Idle for 2 minutes; any keystroke wakes it |

`Companion` is plain Python with an injectable clock: `SensaiApp` sets its base
mood (`set_mood()`) or a passing one (`flash()`), and `PromptInput` redraws the
frame every 0.2s. To change a face, edit `ANIMATIONS` in `companion.py`: keep
the face as the last 5 cells and props on its left, so the face doesn't move,
and only use single-width characters (`test_companion.py` checks both).

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
`case` in `SensaiApp._render()` and, if needed, a widget in `widgets/`.
Unknown events are ignored until then.
