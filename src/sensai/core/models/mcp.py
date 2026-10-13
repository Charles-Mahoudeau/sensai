"""Immutable models describing the MCP servers the app connects to."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class McpServerStatus:
    """Describe the outcome of connecting to an MCP server.

    Attributes:
        name: The server's name, prefixed to its tools' names.
        url: Where the server was reached, or tried.
        connected: Whether its tools were registered.
        tool_count: How many tools it exposes; 0 when not connected.
        error: Why the connection failed, if it did.
    """

    name: str
    url: str
    connected: bool
    tool_count: int = 0
    error: str | None = None
