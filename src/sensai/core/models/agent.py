"""Agent-related models shared by the engine, the agents and the front-ends."""

from __future__ import annotations

from enum import Enum


class ThinkingEffort(Enum):
    """How much the agent reasons before answering.

    Attributes:
        level: The maximum number of think/act cycles of a turn.
        label: The human-readable name shown to the user.
    """

    NONE = 0, "No thinking"
    LOW = 2, "Quick thinking"
    MEDIUM = 5, "Medium thinking"
    HIGH = 12, "Deep thinking"
    ULTRA = 30, "Ultra thinking"

    def __init__(self, level: int, label: str) -> None:
        """Store the cycle budget and the display label."""
        self.level = level
        self.label = label

    def next(self) -> ThinkingEffort:
        """Return the next effort, from the lowest to the highest, then wrap."""
        members = list(ThinkingEffort)
        return members[(members.index(self) + 1) % len(members)]
