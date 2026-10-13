"""Text formatting shared by the transcript widgets."""


def trim(text: str, limit: int) -> str:
    """Collapse whitespace into a single line and cut it at ``limit`` characters."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"
