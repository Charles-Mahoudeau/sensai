from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    # content: str = "" on peut ajouter un content mais a voir car on ne doit pas tout renvoyer

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("WebSearchResult.title must be a non-empty string")
        if not self.url:
            raise ValueError("WebSearchResult.url must be a non-empty string")
