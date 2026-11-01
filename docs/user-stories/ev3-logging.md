# [EV3] Logging: user stories

Design: [docs/adapters/tui.md](../adapters/tui.md).
End user: [Titouan](../user-profile.md). The logs are read by the Sensai team for him.

EV3 is only partly implemented: the session's logs are shown live in the chat, but there is no
structured log file and no metrics dashboard yet. It is not counted as a finished feature.

## EV3-1 · See what Sensai does, without leaving the chat

**As** a Sensai team member who reproduces a problem Titouan reported (a missing tool, a wrong
answer),
**I want** to read the session's logs live inside the chat, filtered by text and level,
**so that** I find which step went wrong while it happens, instead of digging through `sensai.log`
after the session.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), a
lone, non-technical user who cannot debug Sensai himself.

Acceptance criteria:

- `/logs` opens, in place of the prompt, a panel listing this session's log records from INFO up,
  one colored line each: time, level, category, message.
- New records appear in the panel while it is open (for example when an MCP server fails).
- Typing filters the records to those whose message or logger contains the text; `ctrl+l` raises
  the lowest level shown, and the border shows how many records are shown and from which level.
- `Esc` closes the panel and gives the prompt back.

Check: `uv run pytest tests/adapters/tui/panels/test_logs.py tests/adapters/tui/test_log_buffer.py tests/adapters/tui/test_log_format.py`

## EV3-2 · Find the slow model calls

**As** a Sensai team member who tries to shorten Titouan's wait on a laptop without a GPU,
**I want** one log line per model request and per reply, with its duration and token counts,
**so that** I see which calls of a turn (ReAct steps, memory extraction, session title) cost the
most time, and which ones to cut or shorten.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system),
hardware and latency.

Acceptance criteria:

- Each model request is logged as `→ <model> · <n> messages`, followed by the tools offered and the
  schema used: `step(<tools>, answer)` for a ReAct step, `schema(facts, forget)` for the memory
  extraction.
- Each reply is logged as `← <duration> s · <prompt tokens> in / <generated tokens> out ·
  <stop reason>`, with the tools called and a short preview of the text.
- After one question, `/logs` with the filter `←` lists every model call of the turn with its
  duration.

Check: `uv run pytest tests/adapters/ollama tests/adapters/tui/panels/test_logs.py`
