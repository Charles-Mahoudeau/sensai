"""Asynchronous broadcast bus for Engine events."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sensai.core.events.types import Event


class EventBus:
    """Broadcast each published event to every current subscriber."""

    def __init__(self) -> None:
        """Initialize the bus without subscribers."""
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> AsyncGenerator[Event]:
        """For an entity for subscribe and receive events."""
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.add(queue)
        return self._drain(queue)

    # CALLED ONLY BY ENGINE'S RUN METHOD
    async def publish(self, event: Event) -> None:
        """Send an event to every subscriber active at publication time."""
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    async def _drain(self, queue: asyncio.Queue[Event]) -> AsyncGenerator[Event]:
        """Yield queued events until the subscriber closes its stream."""
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
