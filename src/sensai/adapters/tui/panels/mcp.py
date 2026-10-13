"""The /mcp panel: the MCP servers and whether they are connected."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.content import Content
from textual.widgets import Static

from sensai.adapters.tui.panels.base import Panel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual.app import ComposeResult

    from sensai.core.models import McpServerStatus

EMPTY_TEXT = "No MCP servers configured"
HINTS = "esc close"


class McpPanel(Panel):
    """List the MCP servers configured at startup, connected or not."""

    def __init__(self, servers: Sequence[McpServerStatus]) -> None:
        """Show `servers`, in the order they were configured."""
        super().__init__(id="mcp-panel", classes="panel")
        self._servers = tuple(servers)

    def compose(self) -> ComposeResult:
        """Lay out one row per server; the counts and hints go in the border."""
        connected = sum(server.connected for server in self._servers)
        self.border_title = Content(f"MCP servers · {connected} connected")
        self.border_subtitle = HINTS
        if not self._servers:
            yield Static(EMPTY_TEXT, classes="panel-empty", markup=False)
        width = max((len(server.name) for server in self._servers), default=0)
        for server in self._servers:
            yield Static(_row(server, width), classes="mcp-server")
            yield Static(server.url, classes="mcp-url", markup=False)


def _row(server: McpServerStatus, width: int) -> Content:
    name = (server.name.ljust(width), "bold")
    if server.connected:
        tools = "tool" if server.tool_count == 1 else "tools"
        return Content.assemble(
            ("● ", "$success"),
            name,
            "   connected   ",
            (f"{server.tool_count} {tools}", "dim"),
        )
    return Content.assemble(
        ("✗ ", "$error"), name, ("   failed: ", "$error"), server.error or "unknown"
    )
