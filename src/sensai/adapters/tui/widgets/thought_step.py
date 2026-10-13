"""One think/act cycle of a `ReasoningGroup`."""

from __future__ import annotations

import textwrap
import time
from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Markdown, Static

from sensai.adapters.tui.widgets._text import trim

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ThoughtStep(Vertical):
    """One think/act cycle: a title, then a live window, a summary or the full text.

    While the thought streams, only its last few lines are shown. Once it is
    done it shrinks to a one-line summary, and the whole text is rendered as
    Markdown when the enclosing group is expanded (see `sensai.tcss`).
    """

    LIVE_LINES = 3
    SUMMARY_LIMIT = 100

    def __init__(self, number: int) -> None:
        """Start streaming, with no reasoning yet."""
        super().__init__()
        self.number = number
        self.text = ""
        self.ready = False
        self._t0 = time.monotonic()
        self._t1: float | None = None
        self._title_line = Static(markup=False, classes="thought-title")
        self._live_line = Static(markup=False, classes="thought-live")
        self._summary_line = Static(markup=False, classes="thought-summary")
        self._full_text = Markdown(classes="thought-full")
        self.add_class("-streaming")

    def compose(self) -> ComposeResult:
        """Lay out the title and the three views of the thought."""
        yield self._title_line
        yield self._live_line
        yield self._summary_line
        yield self._full_text

    def on_mount(self) -> None:
        """Show the initial title."""
        self.refresh_title()

    @property
    def streaming(self) -> bool:
        """Tell whether the thought is still being generated."""
        return self._t1 is None

    @property
    def elapsed(self) -> float:
        """Seconds spent on this thought so far, or in total once finished."""
        return (self._t1 or time.monotonic()) - self._t0

    @property
    def title(self) -> str:
        """The step title: its number, its duration and whether it was ready."""
        title = f"Step {self.number} · {self.elapsed:.0f}s"
        return f"{title} · ready to answer" if self.ready else title

    def refresh_title(self) -> None:
        """Redraw the title, e.g. for the running clock."""
        self._title_line.update(self.title)

    def add_fragment(self, fragment: str) -> None:
        """Append a streamed fragment and slide the live window."""
        self.text += fragment
        self._live_line.update(self._tail())

    def mark_ready(self) -> None:
        """Record that this thought concluded the answer can be written."""
        self.ready = True
        self.refresh_title()

    async def finish(self) -> None:
        """Stop the clock and swap the live window for the summary and full text."""
        if not self.streaming:
            return
        self._t1 = time.monotonic()
        self.text = self.text.strip()
        self.remove_class("-streaming")
        self.add_class("-done")
        self.refresh_title()
        self._summary_line.update(trim(self.text, self.SUMMARY_LIMIT))
        await self._full_text.update(self.text)

    def _tail(self) -> str:
        """The last lines of the thought, wrapped to the current width."""
        width = max(20, self.size.width - 4 if self.size.width else 80)
        lines = textwrap.wrap(" ".join(self.text.split()), width=width)
        tail = lines[-self.LIVE_LINES :]
        if len(lines) > len(tail):
            tail[0] = "…" + tail[0]
        return "\n".join(tail)
