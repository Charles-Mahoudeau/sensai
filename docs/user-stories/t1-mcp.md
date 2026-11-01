# [T1] MCP and tools: user stories

Design and usage: [docs/adapters/tui.md](../adapters/tui.md#panels).
Target user: [Titouan](../user-profile.md).

## T1-1 · Plug in a new tool service through the configuration

**As** a Sensai team member who adds tools useful to Titouan (an exercise bank, a calculation
checker…),
**I want** to declare any HTTP MCP server in the configuration file,
**so that** I can offer new tools to the tutor without changing the code, and without ever writing
a secret in a versioned file.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he
reads": reliable tools rather than the model doing calculations in its head.

Acceptance criteria:

- Each `[mcp.servers.<name>]` table in `config/sensai.toml` declares one server with a `url` and an
  optional `token_env`; its tools appear in `/tools` as `<name>__<tool>`.
- The token is read from the environment variable named by `token_env` (or from `.env`), never
  from the TOML file.
- A server whose `token_env` variable is unset is skipped, with a warning in `sensai.log`.
- An invalid table (unknown key, missing `url`) stops Sensai at start-up with an error naming the
  faulty key.

Check: `uv run pytest tests/test_config.py tests/core/tools/test_mcp.py`

## T1-2 · The model uses an MCP tool in the middle of its answer

**As** Titouan, who needs exact results to learn the right method,
**I want** Sensai to call an external tool on its own when it needs one, then rely on its result
to answer,
**so that** I do not learn a method from a wrong result that a small model worked out in its head.

Link to the scenario: [typical session](../user-profile.md#a-typical-session), step 4 (checking
his answer).

Acceptance criteria:

- With `uv run python scripts/fake_mcp_server.py` running, the request « Utilise l'outil echo pour
  répéter "bonjour" » shows the `fake__echo` call in the reasoning block, with its result, and the
  server prints the request it received.
- The final answer uses the result returned by the tool.
- With a third-party server (the GitHub MCP server, with `GITHUB_TOKEN` set), its tools appear in
  `/tools` and a call works the same way.
- A server that goes down during a call produces a failed tool result; the turn ends with an
  answer (see [A1-3](a1-react.md)).

Check: `uv run pytest tests/adapters/mcp tests/core/tools/test_mcp.py`, then the manual test with
`scripts/fake_mcp_server.py`.

> To do: replace the `echo` server with an MCP server of Sensai's own that is useful to Titouan,
> and check the connection to a third-party MCP server other than GitHub. The current client only
> speaks the HTTP transport and protocol version `2026-07-28`.

## T1-3 · Know which tool services are available

**As** Titouan, who starts Sensai alone and does not read logs,
**I want** to see which tool servers are connected, and why one is not,
**so that** I understand why a tool is missing instead of thinking Sensai cannot do it.

Link to the scenario: [constraints](../user-profile.md#constraints-this-puts-on-the-system), a
lone, non-technical user.

Acceptance criteria:

- `/mcp` opens, in place of the prompt, a panel listing each configured server with its URL.
- A connected server shows its number of tools; a failed server shows why (for example the `fake`
  server when `scripts/fake_mcp_server.py` is not running).
- A server that cannot be reached does not stop Sensai from starting.
- `Esc` closes the panel and gives the prompt back.

Check: `uv run pytest tests/adapters/tui/commands/test_builtin.py tests/core/tools/test_mcp.py`

## T1-4 · Choose the tools the tutor may use

**As** Titouan, who is doing graded homework,
**I want** to enable and disable tools one by one or all at once,
**so that** Sensai helps me with the method from the course rather than with a solution found
online, when I really want to practise on my own.

Link to the scenario: [his problem](../user-profile.md#his-problem), "they give the answer, not
the method".

Acceptance criteria:

- `/tools` opens a panel showing `Tools · n/m enabled` and every tool, grouped by source, with its
  description.
- `Space`, `Enter` or a click toggles the highlighted tool; the counts update at once.
- The Enable all / Disable all buttons (`ctrl+a` / `ctrl+d`) change every tool; with a filter
  typed, only the tools shown.
- A disabled tool is no longer offered to the model from the next message: after disabling
  `web_search`, « Cherche sur internet la correction de cet exercice » triggers no `web_search`
  call.
- Every tool is enabled again at the next start, except with `--no-tools`.

Check: `uv run pytest tests/adapters/tui/commands/test_builtin.py tests/core/tools/test_registry.py`

## T1-5 · Sensai uses a calculator instead of calculating in its head

**As** Titouan, who checks his homework against Sensai's numbers,
**I want** Sensai to call a calculator for every calculation and give its result as returned,
**so that** I never copy a wrong number that a small model made up while calculating mentally.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he
reads", and [typical session](../user-profile.md#a-typical-session), step 4 (checking his answer).

Acceptance criteria:

- « Combien font (12,5 × 4)² / √16 ? » shows a `calculator` call in the reasoning block, and the
  answer gives 625, the value the tool returned.
- An exact result is returned after `=` (`2 ^ 10 = 1024`), a rounded one after `≈`
  (`sqrt 2 ≈ 1.4142135623731`), so Titouan knows when a value is approximate.
- `calculator` is listed in `/tools` and can be disabled there like any other tool.

Check: `uv run pytest tests/core/tools/builtin/test_calculator.py`

## T1-6 · A calculator that refuses instead of giving a wrong number

**As** Titouan, who sometimes types an impossible or badly written calculation,
**I want** the calculator to report an error instead of returning a result,
**so that** Sensai tells me what is wrong with my calculation rather than answering with a number
that means nothing.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he
reads".

Acceptance criteria:

- `1 / 0` returns a `ZeroDivisionError` error result, even inside a longer expression
  (`1 / 0 + 1`).
- An empty, malformed (`5 +`) or non-arithmetic expression (`__import__('os')`) is refused as an
  error; nothing is executed.
- An equation with an unknown (`x + 2 = 5`) is refused: the calculator does not solve equations.
- A result too large (`10 ^ 4001`) or one that underflows to zero (`e ^ -800`) is refused instead of
  being returned as a false value.
- After an error, the turn still ends with an answer that says what went wrong (see
  [A1-3](a1-react.md)).

Check: `uv run pytest tests/core/tools/builtin/test_calculator.py`
