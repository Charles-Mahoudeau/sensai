"""Built-in tools for persistent long-term memory."""

from typing import TYPE_CHECKING

from sensai.core.tools.builtin.memory import create, delete, read, update

if TYPE_CHECKING:
    from sensai.core.ports import MemoryRepository
    from sensai.core.tools.registry import ToolRegistry


def register_self(tool_registry: ToolRegistry, memory: MemoryRepository) -> None:
    """Register persistent-memory CRUD tools in a shared registry."""
    tool_registry.register(create.spec(), create.handler(memory))
    tool_registry.register(read.spec(), read.handler(memory))
    tool_registry.register(update.spec(), update.handler(memory))
    tool_registry.register(delete.spec(), delete.handler(memory))
