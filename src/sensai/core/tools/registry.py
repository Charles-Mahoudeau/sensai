"""Registry and dispatch logic for built-in tools."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sensai.core.models import ToolCall, ToolInfo, ToolOutput, ToolResult, ToolSpec
from sensai.core.tools.permissions import AllowAll, PermissionPolicy

type ToolHandler = Callable[[Mapping[str, Any]], Awaitable[str | ToolOutput]]

BUILTIN_SOURCE = "builtin"


@dataclass(slots=True)
class _Entry:
    spec: ToolSpec
    handler: ToolHandler
    source: str
    enabled: bool = True


class ToolRegistry:
    """Register tools and dispatch authorized calls to their handlers."""

    def __init__(self, permissions: PermissionPolicy | None = None) -> None:
        """Create a registry with the provided permission policy."""
        self._permissions = permissions or AllowAll()
        self._tools: dict[str, _Entry] = {}

    def register(
        self, spec: ToolSpec, handler: ToolHandler, *, source: str = BUILTIN_SOURCE
    ) -> None:
        """Register a tool handler under the specification's name, enabled.

        Args:
            spec: The tool's specification; its name must be unique.
            handler: Called with the arguments of each call to the tool.
            source: Where the tool comes from: `builtin`, or an MCP server's name.

        Raises:
            ValueError: A tool with the same name is already registered.
        """
        if spec.name in self._tools:
            raise ValueError(f"Tool with name {spec.name} is already registered")
        self._tools[spec.name] = _Entry(spec, handler, source)

    def spec(self) -> tuple[ToolSpec, ...]:
        """Return the specifications of the enabled tools, offered to the model."""
        return tuple(entry.spec for entry in self._tools.values() if entry.enabled)

    def tools(self) -> tuple[ToolInfo, ...]:
        """Return every registered tool, enabled or not, in registration order."""
        return tuple(
            ToolInfo(entry.spec, entry.source, entry.enabled)
            for entry in self._tools.values()
        )

    def set_enabled(self, name: str, *, enabled: bool) -> None:
        """Enable or disable one tool.

        Raises:
            KeyError: No tool is registered under `name`.
        """
        entry = self._tools.get(name)
        if entry is None:
            raise KeyError(f"Unknown tool {name!r}")
        entry.enabled = enabled

    def set_all_enabled(
        self, *, enabled: bool, names: Iterable[str] | None = None
    ) -> None:
        """Enable or disable several tools at once.

        Args:
            enabled: The state to set.
            names: The tools to change; every tool when None.

        Raises:
            KeyError: One of `names` is not a registered tool; nothing changed.
        """
        if names is None:
            entries = list(self._tools.values())
        else:
            names = list(names)
            unknown = [name for name in names if name not in self._tools]
            if unknown:
                raise KeyError(f"Unknown tools {unknown!r}")
            entries = [self._tools[name] for name in names]
        for entry in entries:
            entry.enabled = enabled

    async def call(self, call: ToolCall) -> ToolResult:
        """Authorize and execute a tool call."""
        entry = self._tools.get(call.name)
        if entry is None:
            return self._error(call, f"Unknown tool {call.name!r}")
        if not entry.enabled:
            return self._error(call, f"Tool {call.name!r} is disabled")

        decision = await self._permissions.check(entry.spec, call)
        if not decision.allowed:
            return self._error(
                call, f"Permission denied: {decision.reason or 'no reason provided'}"
            )

        return await self._call_handler(entry.handler, call)

    @staticmethod
    async def _call_handler(handler: ToolHandler, call: ToolCall) -> ToolResult:
        try:
            output = await handler(call.arguments)
        except Exception as exc:
            return ToolRegistry._error(call, f"{type(exc).__name__}: {exc}")
        if isinstance(output, str):
            return ToolResult(call.name, output, call_id=call.id or "")
        return ToolResult(
            call.name,
            output.content,
            call_id=call.id or "",
            is_error=output.is_error,
            attachments=output.attachments,
        )

    @staticmethod
    def _error(call: ToolCall, message: str) -> ToolResult:
        return ToolResult(call.name, message, is_error=True, call_id=call.id or "")
