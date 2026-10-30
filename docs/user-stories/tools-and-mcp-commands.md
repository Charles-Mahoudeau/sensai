# Tools and MCP servers in the TUI: user stories

Design and usage: [docs/adapters/tui.md](../adapters/tui.md#panels).

## Configure the MCP servers

As a user, I want to declare any HTTP MCP server in the configuration file, so that I can plug
Sensai into new tool sources without touching the code.

Acceptance criteria:

- Each `[mcp.servers.<name>]` table in `config/sensai.toml` declares one server with a `url` and
  an optional `token_env`; its tools appear as `<name>__<tool>`.
- The bearer token is read from the environment variable `token_env` names, never from the file.
- A server whose `token_env` variable is unset is skipped with a warning.
- An invalid server table makes Sensai exit with an error naming the offending key.

## See which MCP servers are connected

As a user, I want to list the MCP servers Sensai uses, so that I know which tools sources are
available and why one is missing.

Acceptance criteria:

- `/mcp` opens a panel in place of the prompt listing each configured server with its URL.
- A connected server shows how many tools it brings; a failed one shows why it failed.
- A server that cannot be reached does not stop Sensai from starting.
- `esc` closes the panel and gives the prompt back.

## Choose which tools the model may use

As a user, I want to enable and disable tools one by one or all at once, so that the model only
uses the tools I trust for the current task.

Acceptance criteria:

- `/tools` opens a panel showing `Tools · n/m enabled` and every tool, grouped by source, with
  its description.
- `space`, `Enter` or a click toggles the highlighted tool; the counts update at once.
- Enable all / Disable all buttons (`ctrl+a` / `ctrl+d`) change every tool; with a filter typed,
  they only change the tools shown.
- A disabled tool is not offered to the model from the next message, and is enabled again at the
  next start.
- MCP tools are named `<server>__<tool>`, so two servers cannot clash.
