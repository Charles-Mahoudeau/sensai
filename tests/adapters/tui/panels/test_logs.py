"""Tests for the live /logs panel."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from textual.app import App
from textual.widgets import RichLog

from sensai.adapters.tui.log_buffer import LogBuffer
from sensai.adapters.tui.panels import LogsPanel, Panel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from textual.app import ComposeResult
    from textual.pilot import Pilot


class _Host(App[None]):
    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self.buffer = buffer
        self.closed = False

    def compose(self) -> ComposeResult:
        yield LogsPanel(self.buffer)

    def on_mount(self) -> None:
        self.query_one(LogsPanel).focus_first()

    def on_panel_closed(self, event: Panel.Closed) -> None:
        del event
        self.closed = True


def _logger(buffer: LogBuffer) -> logging.Logger:
    logger = logging.getLogger("sensai.adapters.tests.panel")
    logger.handlers = [buffer]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def _lines(app: _Host) -> list[str]:
    """The messages shown, without the time, level and category columns."""
    return [line.text.split("  ")[-1] for line in app.query_one(RichLog).lines]


def _run(
    buffer: LogBuffer, scenario: Callable[[_Host, Pilot[None]], Awaitable[None]]
) -> None:
    async def run() -> None:
        app = _Host(buffer)
        async with app.run_test() as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(run())


def test_records_so_far_are_shown_from_info_up() -> None:
    """Opening the panel shows the buffered records, without DEBUG."""
    buffer = LogBuffer()
    logger = _logger(buffer)
    logger.debug("noise")
    logger.info("started")
    logger.warning("careful")

    async def scenario(app: _Host, pilot: Pilot[None]) -> None:
        del pilot
        assert _lines(app) == ["started", "careful"]
        assert str(app.query_one(LogsPanel).border_title) == "Logs · 2 shown · INFO+"

    _run(buffer, scenario)


def test_new_records_appear_while_the_panel_is_open() -> None:
    """A record logged after opening is appended live."""
    buffer = LogBuffer()
    logger = _logger(buffer)

    async def scenario(app: _Host, pilot: Pilot[None]) -> None:
        logger.info("live")
        await pilot.pause()
        assert _lines(app) == ["live"]

    _run(buffer, scenario)


def test_typing_filters_and_ctrl_l_raises_the_level() -> None:
    """The filter matches messages; ctrl+l cycles the lowest level shown."""
    buffer = LogBuffer()
    logger = _logger(buffer)
    logger.info("run_python started")
    logger.info("chat done")
    logger.warning("run_python failed")

    async def scenario(app: _Host, pilot: Pilot[None]) -> None:
        await pilot.press(*"run_python")
        assert _lines(app) == ["run_python started", "run_python failed"]

        await pilot.press("ctrl+l")
        assert _lines(app) == ["run_python failed"]
        assert str(app.query_one(LogsPanel).border_title).endswith("WARNING+")

    _run(buffer, scenario)


def test_escape_closes_and_stops_following() -> None:
    """Esc asks to close; once removed, the panel no longer listens."""
    buffer = LogBuffer()
    logger = _logger(buffer)

    async def scenario(app: _Host, pilot: Pilot[None]) -> None:
        await pilot.press("escape")
        assert app.closed
        await app.query_one(LogsPanel).remove()
        logger.info("after")
        await pilot.pause()

    _run(buffer, scenario)
    assert buffer._listeners == []
