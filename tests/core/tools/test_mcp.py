"""Tests for registering an MCP server's tools."""

from __future__ import annotations

import asyncio

from sensai.core.models import McpServerStatus, ToolCall, ToolSpec
from sensai.core.tools.mcp import register_mcp_server
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeMcpClient


def test_tools_are_namespaced_and_calls_use_the_original_name() -> None:
    """`get_me` of `github` becomes `github__get_me` and is forwarded back."""
    registry = ToolRegistry()
    client = FakeMcpClient(
        "github",
        [ToolSpec("get_me", "Get me"), ToolSpec("fork", "Fork")],
        answer="octocat",
    )

    async def run() -> tuple[McpServerStatus, str]:
        status = await register_mcp_server(registry, client)
        result = await registry.call(ToolCall("github__get_me", {"a": 1}))
        return status, result.content

    status, content = asyncio.run(run())

    assert status == McpServerStatus(
        "github", "https://mcp.test/", connected=True, tool_count=2
    )
    assert [(t.spec.name, t.source) for t in registry.tools()] == [
        ("github__get_me", "github"),
        ("github__fork", "github"),
    ]
    assert content == "octocat"
    assert client.calls == [("get_me", {"a": 1})]


def test_unreachable_server_is_reported_not_raised() -> None:
    """A server that cannot connect adds no tool and reports why."""
    registry = ToolRegistry()
    client = FakeMcpClient("notion", [ToolSpec("search", "")], unavailable=True)

    status = asyncio.run(register_mcp_server(registry, client))

    assert not status.connected
    assert status.tool_count == 0
    assert status.error == "notion: connection refused"
    assert registry.tools() == ()
