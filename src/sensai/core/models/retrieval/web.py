"""Immutable models returned by web search adapters."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    # content: str = "" on peut ajouter un content sauf si pas tout renvoyer

    def __post_init__(self) -> None:
        """Require the fields needed to identify the result."""
        if not self.title:
            raise ValueError("WebSearchResult.title must be a non-empty string")
        if not self.url:
            raise ValueError("WebSearchResult.url must be a non-empty string")
