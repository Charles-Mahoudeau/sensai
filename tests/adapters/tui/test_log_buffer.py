"""Tests for the in-memory log buffer behind /logs."""

from __future__ import annotations

import logging

from sensai.adapters.tui.log_buffer import LogBuffer


def _logger(buffer: LogBuffer) -> logging.Logger:
    logger = logging.getLogger("sensai.tests.log_buffer")
    logger.handlers = [buffer]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def test_records_are_kept_oldest_first_up_to_the_capacity() -> None:
    """Past the capacity, the oldest records are dropped."""
    buffer = LogBuffer(capacity=2)
    logger = _logger(buffer)

    for text in ("one", "two", "three"):
        logger.info(text)

    assert [r.getMessage() for r in buffer.records] == ["two", "three"]


def test_records_below_the_level_are_ignored() -> None:
    """The handler level filters records, as for any handler."""
    buffer = LogBuffer(logging.INFO)
    logger = _logger(buffer)

    logger.debug("hidden")
    logger.warning("shown")

    assert [r.getMessage() for r in buffer.records] == ["shown"]


def test_listeners_get_new_records_until_they_unsubscribe() -> None:
    """A subscriber sees each new record, and nothing after unsubscribing."""
    buffer = LogBuffer()
    logger = _logger(buffer)
    seen: list[str] = []

    unsubscribe = buffer.subscribe(lambda record: seen.append(record.getMessage()))
    logger.info("first")
    unsubscribe()
    logger.info("second")

    assert seen == ["first"]
    assert len(buffer.records) == 2
