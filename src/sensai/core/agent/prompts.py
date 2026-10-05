"""The prompt texts the ReAct agent sends to the model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from sensai.core.prompts.defaults import (
    REACT_ANSWER,
    REACT_NOTES,
    REACT_THOUGHT,
    load_defaults,
)

if TYPE_CHECKING:
    from sensai.core.prompts import PromptLibrary


@dataclass(frozen=True, slots=True)
class AgentPrompts:
    """The three ReAct prompts, usually the active versions from the library.

    Attributes:
        thought: Asks for a private thought before acting; filled with `{tools}`.
        notes: Wraps that thought for the acting call; filled with `{thought}`.
        answer: Asks for the final answer after tool results.
    """

    thought: str
    notes: str
    answer: str

    @classmethod
    def defaults(cls) -> Self:
        """Return the defaults shipped with the code (no database needed)."""
        texts = load_defaults()
        return cls(
            thought=texts[REACT_THOUGHT],
            notes=texts[REACT_NOTES],
            answer=texts[REACT_ANSWER],
        )

    @classmethod
    async def active(cls, library: PromptLibrary) -> Self:
        """Return the active version of each ReAct prompt.

        Raises:
            PromptNotFoundError: A ReAct prompt has no active version.
        """
        return cls(
            thought=(await library.active(REACT_THOUGHT)).content,
            notes=(await library.active(REACT_NOTES)).content,
            answer=(await library.active(REACT_ANSWER)).content,
        )
