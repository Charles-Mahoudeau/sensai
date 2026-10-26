"""Shows the stored memories to the model in the system message.

Small models overlook a memory that reaches them as the result of a tool call
they never made, but they use what the system message states, as they do with
the user profile. So before each turn the stored records are written there.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sensai.core.agent.prompts import MemoryPrompts
from sensai.core.ports import StorageError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.memory import MemoryRecord
    from sensai.core.ports import MemoryRepository

# Enough for what a personal assistant knows about its user, while leaving most
# of a small model's context to the conversation.
_DEFAULT_LIMIT = 20

_logger = logging.getLogger("MemoryRecall")


@dataclass(frozen=True, slots=True)
class Recollection:
    """The memories shown to the model for one turn.

    Attributes:
        text: The block appended to the system message; empty when there is
            nothing to show.
        complete: Whether every stored memory is in `text`, so a memory search
            could find nothing more.
    """

    text: str
    complete: bool


class MemoryRecall:
    """Selects the stored memories to show and writes them for the model."""

    def __init__(
        self,
        memory: MemoryRepository,
        *,
        limit: int = _DEFAULT_LIMIT,
        title: str | None = None,
    ) -> None:
        """Store where the memories are and how many to show at most.

        Args:
            memory: The stored records.
            limit: The most records shown in one turn.
            title: The `memory_recall` prompt, written above the memories; the
                code default when `None`.
        """
        self._memory = memory
        self._limit = limit
        self._title = title or MemoryPrompts.defaults().recall

    async def recall(self, request: str) -> Recollection:
        """Return every stored memory, or the most relevant ones past `limit`.

        Past the limit, the records matching `request` come first, then the
        most recently updated ones. A storage failure shows nothing and is
        logged: the answer the user is waiting for must not depend on it.
        """
        try:
            stored = list(await self._memory.find())
            complete = len(stored) <= self._limit
            if not complete:
                relevant = await self._memory.find(query=request)
                by_id = {record.id: record for record in [*relevant, *stored]}
                stored = list(by_id.values())[: self._limit]
        except StorageError as error:
            _logger.warning("Could not recall memories: %s", error)
            return Recollection("", complete=False)
        return Recollection(_render(self._title, stored), complete=complete)


def _render(title: str, records: Sequence[MemoryRecord]) -> str:
    """List the records under a title.

    No id: the model doesn't write memory, and could repeat it to the user.
    """
    if not records:
        return ""
    lines = [title]
    for record in records:
        fact = record.name
        if record.description:
            fact += f": {record.description}"
        lines.append(f"- {fact}")
    return "\n".join(lines)
