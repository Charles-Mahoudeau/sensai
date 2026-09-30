"""Web search tool."""

import asyncio
from typing import TYPE_CHECKING, Any

from ddgs import DDGS

from sensai.core.models import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.tools.registry import ToolRegistry


def register_self(tool_registry: ToolRegistry) -> None:
    """Registers the web search tool into a tool registry."""
    tool_registry.register(
        ToolSpec(
            name="web_search",
            description="Searches the web for information.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            requires_confirmation=False,
        ),
        handler=_web_search,
    )


async def _web_search(args: Mapping[str, Any]) -> str:
    query = args.get("query")
    if not query:
        return "Invalid query."

    def _search() -> str:
        with DDGS() as ddgs:
            return str(ddgs.text(str(query)))

    return await asyncio.to_thread(_search)
