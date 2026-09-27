"""Tests for the asynchronous Engine event bus."""

from __future__ import annotations

import asyncio

from sensai.core.events import EventBus, TokenGenerated


def test_publish_broadcasts_to_every_subscriber() -> None:
    """Every subscriber receives the same published event."""

    async def run() -> None:
        bus = EventBus()
        first = bus.subscribe()
        second = bus.subscribe()
        event = TokenGenerated("submission", "Bonjour")

        await bus.publish(event)

        assert await anext(first) == event
        assert await anext(second) == event
        await first.aclose()
        await second.aclose()

    asyncio.run(run())
