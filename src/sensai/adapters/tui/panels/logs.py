"""The /logs panel: this session's log records, live and colored."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.content import Content
from textual.message import Message
from textual.widgets import Input, RichLog

from sensai.adapters.tui.log_format import format_record
from sensai.adapters.tui.panels.base import Panel

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from sensai.adapters.tui.log_buffer import LogBuffer

HINTS = "type to filter · ^l level · esc close"
LEVELS = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR)


class LogsPanel(Panel):
    """Show the buffered log records, then each new one as it is logged.

    Typing narrows the records to those whose message or logger contains the
    text; ctrl+l cycles the lowest level shown.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+l", "cycle_level", "Level", show=False, priority=True),
    ]

    class Added(Message):
        """A record was logged while the panel is open."""

        def __init__(self, record: logging.LogRecord) -> None:
            """Carry the new record."""
            super().__init__()
            self.record = record

    def __init__(self, buffer: LogBuffer) -> None:
        """Show the records of `buffer`, from INFO up."""
        super().__init__(id="logs-panel", classes="panel")
        self._buffer = buffer
        self._level = logging.INFO
        self._filter = ""
        self._shown = 0
        self._unsubscribe: Callable[[], None] | None = None

    def compose(self) -> ComposeResult:
        """Lay out the filter above the records; the hints go in the border."""
        yield Input(placeholder="Filter logs…", id="logs-filter", compact=True)
        yield RichLog(id="logs-view", wrap=True, auto_scroll=True)

    def on_mount(self) -> None:
        """Show the records so far, then follow new ones."""
        self.border_subtitle = HINTS
        self._unsubscribe = self._buffer.subscribe(self._follow)
        self._refresh()

    def on_unmount(self) -> None:
        """Stop following the buffer."""
        if self._unsubscribe is not None:
            self._unsubscribe()

    def focus_first(self) -> None:
        """Focus the filter, so typing narrows the records."""
        self.query_one("#logs-filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show only the records matching the new filter."""
        event.stop()
        self._filter = event.value.strip().lower()
        self._refresh()

    def on_logs_panel_added(self, event: Added) -> None:
        """Append a new record if it matches."""
        if self._matches(event.record):
            self.query_one(RichLog).write(format_record(event.record))
            self._shown += 1
            self._set_title()

    def action_cycle_level(self) -> None:
        """Show records from the next level up, back to DEBUG after ERROR."""
        self._level = LEVELS[(LEVELS.index(self._level) + 1) % len(LEVELS)]
        self._refresh()

    def _follow(self, record: logging.LogRecord) -> None:
        # Records may come from worker threads: post_message is thread-safe.
        self.post_message(self.Added(record))

    def _matches(self, record: logging.LogRecord) -> bool:
        if record.levelno < self._level:
            return False
        text = f"{record.name} {record.getMessage()}".lower()
        return self._filter in text

    def _refresh(self) -> None:
        view = self.query_one(RichLog)
        view.clear()
        shown = [record for record in self._buffer.records if self._matches(record)]
        for record in shown:
            view.write(format_record(record))
        self._shown = len(shown)
        self._set_title()

    def _set_title(self) -> None:
        level = logging.getLevelName(self._level)
        self.border_title = Content(f"Logs · {self._shown} shown · {level}+")
