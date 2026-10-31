"""Keep the latest log records in memory, for the /logs panel."""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

CAPACITY = 1000
"""How many records are kept; older ones are dropped."""

type Listener = Callable[[logging.LogRecord], None]


class LogBuffer(logging.Handler):
    """A logging handler that keeps recent records and tells listeners of new ones.

    Records may be emitted from worker threads, so listeners must be
    thread-safe (posting a Textual message is).
    """

    def __init__(self, level: int = logging.NOTSET, capacity: int = CAPACITY) -> None:
        """Keep up to `capacity` records of at least `level`."""
        super().__init__(level)
        self._records: deque[logging.LogRecord] = deque(maxlen=capacity)
        self._listeners: list[Listener] = []

    @property
    def records(self) -> tuple[logging.LogRecord, ...]:
        """The kept records, oldest first."""
        return tuple(self._records)

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call `listener` with every new record; returns how to stop."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def emit(self, record: logging.LogRecord) -> None:
        """Keep `record` and pass it to every listener."""
        self._records.append(record)
        for listener in tuple(self._listeners):
            listener(record)
