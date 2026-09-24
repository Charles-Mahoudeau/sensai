"""Permission policies for built-in tool execution."""

from __future__ import annotations

from typing import Protocol

from sensai.core.models import PermissionDecision, ToolCall, ToolSpec


class PermissionPolicy(Protocol):
    """Define the interface used to authorize tool calls."""

    async def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
        """Return the authorization decision for a tool call."""
        ...


class AllowAll:  # Basicely no permissions, default for registery
    """Allow all permissions. Always grants any request."""

    async def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
        """Allow the tool call."""
        return PermissionDecision(allowed=True)


class DenyAll:
    """Cancel all permissions. Always denies any request."""

    async def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
        """Deny the tool call."""
        return PermissionDecision(allowed=False)


# Example of a future permission policy that could implement complex logic.

# class FuturePermissionPolicy:
#     async def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision:
#         # Implement custom permission logic here
#         return PermissionDecision(allowed=True)


# Example of futur handler usage :

# decision = await self._permissions.check(spec, call)
# if not decision.allowed:
#     return self._error(call, f"Permission denied: {
#       decision.reason or 'not allowed'}")
