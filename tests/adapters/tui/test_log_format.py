"""Tests for the colored log lines of /logs."""

from __future__ import annotations

import logging
import sys

import pytest

from sensai.adapters.tui.log_format import category, format_record


def _record(name: str, level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, message, (), None)


@pytest.mark.parametrize(
    ("logger", "expected"),
    [
        ("sensai.adapters.ollama.chat", "ollama"),
        ("sensai.core.agent.re_act", "agent"),
        ("sensai.app", "app"),
        ("httpx", "httpx"),
    ],
)
def test_category_is_the_first_part_after_the_package(
    logger: str, expected: str
) -> None:
    """Package and zone prefixes are dropped, then the name is cut at its dot."""
    assert category(logger) == expected


def test_a_line_has_time_level_category_and_message() -> None:
    """The columns are padded so that messages line up."""
    text = format_record(_record("sensai.adapters.ollama.chat", logging.INFO, "hi"))

    time_part, rest = text.plain.split("  ", 1)
    assert len(time_part) == len("21:35:42")
    assert rest == "INFO   ollama     hi"


def test_levels_and_categories_are_colored() -> None:
    """A warning is yellow, and a known category gets its own color."""
    text = format_record(_record("sensai.adapters.mcp.http", logging.WARNING, "x"))

    styles = {
        text.plain[span.start : span.end].strip(): span.style for span in text.spans
    }
    assert styles["WARN"] == "yellow"
    assert styles["mcp"] == "cyan"


def test_an_exception_follows_the_message() -> None:
    """The traceback is shown on the next lines."""
    record = _record("sensai.app", logging.ERROR, "failed")
    try:
        raise ValueError("boom")
    except ValueError:
        record.exc_info = sys.exc_info()

    text = format_record(record)

    first, *rest = text.plain.splitlines()
    assert first.endswith("failed")
    assert rest[-1] == "ValueError: boom"
