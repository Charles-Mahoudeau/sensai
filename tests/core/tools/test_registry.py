"""Tests for the tool registry: sources, enabling and dispatch."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.models import ToolCall, ToolInfo, ToolSpec
from sensai.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any


async def _echo(arguments: Mapping[str, Any]) -> str:
    return f"echo {dict(arguments)}"


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolSpec("search", "Search the web"), _echo)
    registry.register(ToolSpec("github__get_me", "Get me"), _echo, source="github")
    registry.register(ToolSpec("github__fork", "Fork"), _echo, source="github")
    return registry


def test_tools_lists_every_tool_with_its_source_enabled() -> None:
    """Tools start enabled; built-in ones have the `builtin` source."""
    registry = _registry()

    assert [(t.spec.name, t.source, t.enabled) for t in registry.tools()] == [
        ("search", "builtin", True),
        ("github__get_me", "github", True),
        ("github__fork", "github", True),
    ]


def test_disabled_tool_is_not_offered_and_cannot_be_called() -> None:
    """spec() leaves a disabled tool out; calling it returns an error result."""
    registry = _registry()

    registry.set_enabled("search", enabled=False)
    result = asyncio.run(registry.call(ToolCall("search", {"q": "x"}, id="1")))

    assert [spec.name for spec in registry.spec()] == [
        "github__get_me",
        "github__fork",
    ]
    assert result.is_error
    assert result.content == "Tool 'search' is disabled"


def test_reenabled_tool_is_offered_and_called_again() -> None:
    """Enabling a tool again restores it."""
    registry = _registry()

    registry.set_enabled("search", enabled=False)
    registry.set_enabled("search", enabled=True)
    result = asyncio.run(registry.call(ToolCall("search", {"q": "x"})))

    assert "search" in [spec.name for spec in registry.spec()]
    assert result.content == "echo {'q': 'x'}"


def test_set_all_enabled_changes_every_tool_or_only_the_named_ones() -> None:
    """Without names every tool changes; with names only those do."""
    registry = _registry()

    registry.set_all_enabled(enabled=False)
    assert registry.spec() == ()

    registry.set_all_enabled(enabled=True, names=(n for n in ["github__fork"]))
    assert [spec.name for spec in registry.spec()] == ["github__fork"]


def test_unknown_names_raise_and_change_nothing() -> None:
    """An unknown name is a KeyError, even among known ones."""
    registry = _registry()

    with pytest.raises(KeyError):
        registry.set_enabled("nope", enabled=False)
    with pytest.raises(KeyError):
        registry.set_all_enabled(enabled=False, names=["search", "nope"])

    assert all(tool.enabled for tool in registry.tools())


def test_short_name_drops_the_source_prefix() -> None:
    """MCP tools are shown without their `<server>__` prefix."""
    spec = ToolSpec("github__get_me", "Get me")

    assert ToolInfo(spec, "github", enabled=True).short_name == "get_me"
    assert ToolInfo(spec, "builtin", enabled=True).short_name == "github__get_me"
