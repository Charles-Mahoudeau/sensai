"""Render log records as colored lines for the /logs panel."""

from __future__ import annotations

import logging
import time
import zlib
from typing import TYPE_CHECKING

from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Mapping

_LEVEL_WIDTH = 5
_CATEGORY_WIDTH = 9
_PREFIXES = ("sensai.", "adapters.", "core.")

LEVEL_STYLES: Mapping[int, str] = {
    logging.DEBUG: "dim",
    logging.INFO: "",
    logging.WARNING: "yellow",
    logging.ERROR: "bold red",
    logging.CRITICAL: "bold red",
}
_LEVEL_NAMES = {logging.WARNING: "WARN", logging.CRITICAL: "CRIT"}

CATEGORY_STYLES: Mapping[str, str] = {
    "ollama": "blue",
    "agent": "magenta",
    "tools": "green",
    "mcp": "cyan",
    "sessions": "yellow",
    "app": "white",
}
_OTHER_STYLES = ("bright_blue", "bright_magenta", "bright_green", "bright_cyan")


def category(logger_name: str) -> str:
    """The short area a logger belongs to.

    `sensai.adapters.ollama.chat` gives `ollama`, `sensai.app` gives `app`.
    """
    name = logger_name
    for prefix in _PREFIXES:
        name = name.removeprefix(prefix)
    return name.split(".", 1)[0]


def format_record(record: logging.LogRecord) -> Text:
    """One colored line: time, level, category, then the message.

    An exception, if any, follows on the next lines.
    """
    area = category(record.name)
    level = _LEVEL_NAMES.get(record.levelno, record.levelname)
    line = Text.assemble(
        (time.strftime("%H:%M:%S", time.localtime(record.created)), "dim"),
        "  ",
        (level.ljust(_LEVEL_WIDTH), _level_style(record.levelno)),
        "  ",
        (area.ljust(_CATEGORY_WIDTH), _category_style(area)),
        "  ",
        record.getMessage(),
    )
    if record.exc_info:
        line.append("\n" + logging.Formatter().formatException(record.exc_info), "red")
    return line


def _level_style(levelno: int) -> str:
    return LEVEL_STYLES.get(levelno, "bold red" if levelno > logging.ERROR else "")


def _category_style(area: str) -> str:
    if area in CATEGORY_STYLES:
        return CATEGORY_STYLES[area]
    return _OTHER_STYLES[zlib.crc32(area.encode()) % len(_OTHER_STYLES)]
