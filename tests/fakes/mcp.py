"""A scripted MCP server, for tests that must not reach the network."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sensai.core.ports import McpUnavailableError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models import ToolSpec


class FakeMcpClient:
    """Expose fixed tools and record the calls made to them.

    Implements the `McpClient` port. Every call returns `answer`; with
    `unavailable`, `connect` fails as an unreachable server would.
    """

    def __init__(
        self,
        name: str,
        tools: Sequence[ToolSpec] = (),
        *,
        url: str = "https://mcp.test/",
        answer: str = "ok",
        unavailable: bool = False,
    ) -> None:
        """Script the server's tools and its answer."""
        self._name = name
        self._url = url
        self._tools = tuple(tools)
        self._answer = answer
        self._unavailable = unavailable
        self.connected = False
        self.closed = False
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def name(self) -> str:
        """Server name, used to namespace its tools."""
        return self._name

    @property
    def url(self) -> str:
        """Where the server pretends to be."""
        return self._url

    async def connect(self) -> None:
        """Connect, or fail when scripted as unavailable."""
        if self._unavailable:
            raise McpUnavailableError(f"{self._name}: connection refused")
        self.connected = True

    async def aclose(self) -> None:
        """Record the close."""
        self.closed = True

    async def list_tools(self) -> Sequence[ToolSpec]:
        """Return the scripted tools."""
        return self._tools

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> str:
        """Record the call and return the scripted answer."""
        self.calls.append((name, dict(arguments)))
        return self._answer


if TYPE_CHECKING:
    from sensai.core.ports import McpClient

    def _conforms(x: FakeMcpClient) -> McpClient:
        return x
