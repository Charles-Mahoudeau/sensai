"""Expose the tools of an MCP server through the tool registry."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from sensai.core.models import SOURCE_SEPARATOR, McpServerStatus
from sensai.core.ports import McpError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.ports import McpClient
    from sensai.core.tools.registry import ToolHandler, ToolRegistry


async def register_mcp_server(
    registry: ToolRegistry, client: McpClient
) -> McpServerStatus:
    """Connect to an MCP server and register its tools, namespaced by its name.

    A tool `get_me` of the server `github` is registered as `github__get_me`,
    with `github` as its source; calls are forwarded under the original name.
    A server that cannot be reached is reported, not raised, so the others
    and the app keep working.

    Args:
        registry: The registry to add the tools to.
        client: The server's client, not connected yet.

    Returns:
        Whether the server connected, and how many tools it brought.
    """
    try:
        await client.connect()
        tools = await client.list_tools()
    except McpError as error:
        logging.getLogger(__name__).warning(
            "MCP server %s unavailable: %s", client.name, error
        )
        return McpServerStatus(
            client.name, client.url, connected=False, error=str(error)
        )
    for tool in tools:
        registry.register(
            dataclasses.replace(
                tool, name=f"{client.name}{SOURCE_SEPARATOR}{tool.name}"
            ),
            _forward(client, tool.name),
            source=client.name,
        )
    return McpServerStatus(
        client.name, client.url, connected=True, tool_count=len(tools)
    )


def _forward(client: McpClient, name: str) -> ToolHandler:
    async def call(arguments: Mapping[str, Any]) -> str:
        return await client.call_tool(name, arguments)

    return call
