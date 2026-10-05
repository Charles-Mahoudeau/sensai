"""Default prompt texts shipped with the code."""

from __future__ import annotations

from importlib.resources import files

SYSTEM = "system"
JUDGE = "judge"


def load_defaults() -> dict[str, str]:
    """Return every default prompt, keyed by name.

    A default is a `defaults/<name>.md` file next to this module; its name is the
    file name without the extension.
    """
    directory = files("sensai.core.prompts").joinpath("defaults")
    return {
        entry.name.removesuffix(".md"): entry.read_text(encoding="utf-8")
        for entry in sorted(directory.iterdir(), key=lambda entry: entry.name)
        if entry.name.endswith(".md")
    }
