"""Port for Model Context Protocol servers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models.tools import ToolSpec


class McpError(SensaiError):
    """Base class for every error raised by an MCP adapter."""


class McpUnavailableError(McpError):
    """The MCP server cannot be started or reached."""


class McpToolError(McpError):
    """The MCP server reported that a tool call failed."""


class McpClient(Protocol):
    """A connection to one MCP server that exposes tools."""

    @property
    def name(self) -> str:
        """Server name, used to namespace its tools."""
        ...

    @property
    def url(self) -> str:
        """Where the server is reached, shown to the user."""
        ...

    async def connect(self) -> None:
        """Start the server connection and perform the MCP handshake.

        Raises:
            McpUnavailableError: The server cannot be started or reached.
        """
        ...

    async def aclose(self) -> None:
        """Close the connection. Safe to call twice or before `connect`."""
        ...

    async def list_tools(self) -> Sequence[ToolSpec]:
        """List the tools the server exposes, under their original names.

        Raises:
            McpUnavailableError: The server cannot be reached.
        """
        ...

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        """Call a tool and return its content flattened to text.

        Args:
            name: The tool's original name, as returned by `list_tools`.
            arguments: The arguments, matching the tool's parameter schema.

        Raises:
            McpUnavailableError: The server cannot be reached.
            McpToolError: The server reported that the tool failed.
        """
        ...
