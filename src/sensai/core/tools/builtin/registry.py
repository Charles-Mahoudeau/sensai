"""Registry and dispatch logic for built-in tools."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from sensai.core.models import ToolCall, ToolResult, ToolSpec
from sensai.core.tools.builtin.permissions import AllowAll, PermissionPolicy

type ToolHandler = Callable[[Mapping[str, Any]], Awaitable[str]]


class ToolRegistry:
    """Register tools and dispatch authorized calls to their handlers."""

    def __init__(self, permissions: PermissionPolicy | None = None) -> None:
        """Create a registry with the provided permission policy."""
        self._permissions = permissions or AllowAll()
        self._tools: dict[str, tuple[ToolSpec, ToolHandler]] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        """Register a tool handler under the specification's name."""
        if spec.name in self._tools:
            raise ValueError(f"Tool with name {spec.name} is already registered")
        self._tools[spec.name] = (spec, handler)

    def spec(self) -> tuple[ToolSpec, ...]:
        """Return the registered tool specifications."""
        return tuple(spec for spec, _ in self._tools.values())

    async def call(self, call: ToolCall) -> ToolResult:
        """Authorize and execute a tool call."""
        entry = self._tools.get(call.name)
        if entry is None:
            return self._error(call, f"Unknown tool {call.name!r}")
        spec, handler = entry

        decision = await self._permissions.check(spec, call)
        if not decision.allowed:
            return self._error(
                call, f"Permission denied: {decision.reason or 'no reason provided'}"
            )

        return await self._call_handler(handler, call)

    @staticmethod
    async def _call_handler(handler: ToolHandler, call: ToolCall) -> ToolResult:
        try:
            content = await handler(call.arguments)
        except Exception as exc:
            return ToolRegistry._error(call, f"{type(exc).__name__}: {exc}")
        return ToolResult(call.name, content, call_id=call.id or "")

    @staticmethod
    def _error(call: ToolCall, message: str) -> ToolResult:
        return ToolResult(call.name, message, is_error=True, call_id=call.id or "")
