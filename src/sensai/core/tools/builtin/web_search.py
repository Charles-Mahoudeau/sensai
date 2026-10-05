"""Web search tool."""

import asyncio
from typing import TYPE_CHECKING, Any

from ddgs import DDGS

from sensai.core.models import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sensai.core.tools.registry import ToolRegistry


_DEFAULT_MAX_RESULTS = 5


def _format_results(results: list[dict[str, Any]]) -> str:
    """Render search results as numbered `title - url - snippet` lines."""
    if not results:
        return "No results found."
    return "\n".join(
        f"{index}. {result.get('title', '')} - {result.get('href', '')} - "
        f"{result.get('body', '')}"
        for index, result in enumerate(results, start=1)
    )


def register_self(tool_registry: ToolRegistry) -> None:
    """Registers the web search tool into a tool registry."""
    tool_registry.register(
        ToolSpec(
            name="web_search",
            description=(
                "Searches the web and returns the top results (title, url, snippet). "
                "Use it for recent news, latest versions, current events, or any "
                "fact that may have changed since your training data."
            ),
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

    try:
        max_results = max(1, int(args.get("max_results", _DEFAULT_MAX_RESULTS)))
    except TypeError, ValueError:
        max_results = _DEFAULT_MAX_RESULTS

    def _search() -> str:
        with DDGS() as ddgs:
            results = ddgs.text(str(query), max_results=max_results)
        return _format_results(results)

    return await asyncio.to_thread(_search)
