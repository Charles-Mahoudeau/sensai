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

    # une entité s'inscris pour recevoir les événements
    def subscribe(self) -> AsyncGenerator[Event]:
        """Return an independent event stream for one subscriber."""
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.add(queue)
        return self._drain(queue)

    # APPELE UNIQUEMENT PAR RUN de engine
    # publish un event dans la queue des suscribers
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
