"""The collapsible reasoning of one turn, and its clickable header."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Static

from sensai.adapters.tui.widgets.thought_step import ThoughtStep

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from sensai.adapters.tui.widgets.tool_call_line import ToolCallLine


class ReasoningHeader(Static):
    """The clickable first line of a `ReasoningGroup`."""

    def on_click(self) -> None:
        """Expand or collapse the group."""
        if isinstance(self.parent, ReasoningGroup):
            self.parent.toggle()


class ReasoningGroup(Vertical):
    """The reasoning of one turn: its thoughts and tool calls, collapsible.

    The group is open while the agent works. When the answer starts it
    collapses to a one-line summary; clicking it, or `ctrl+t`, reads the thoughts.
    """

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self) -> None:
        """Start open and live, with nothing inside."""
        super().__init__()
        self.live = True
        self.expanded = False
        self.steps: list[ThoughtStep] = []
        self.tool_count = 0
        self._t0 = time.monotonic()
        self._t1: float | None = None
        self._frame = 0
        self._timer: Timer | None = None
        self._header = ReasoningHeader(markup=False, classes="reasoning-header")
        self._body = Vertical(classes="reasoning-body")
        self._sync()

    def compose(self) -> ComposeResult:
        """Lay out the header above the body."""
        yield self._header
        yield self._body

    def on_mount(self) -> None:
        """Animate the spinner and the clocks while the group is live."""
        self._timer = self.set_interval(0.1, self._tick)
        self.refresh_header()

    @property
    def header_text(self) -> str:
        """The text of the header line."""
        elapsed = f"{(self._t1 or time.monotonic()) - self._t0:.0f}s"
        if self.live:
            spinner = self.SPINNER[self._frame % len(self.SPINNER)]
            return f"{spinner} Reasoning · step {len(self.steps)} · {elapsed}"
        steps = f"{len(self.steps)} step{'s' if len(self.steps) != 1 else ''}"
        parts = [steps]
        if self.tool_count:
            parts.append(f"{self.tool_count} tool{'s' if self.tool_count > 1 else ''}")
        arrow = "▾" if self.expanded else "▸"
        return f"{arrow} Reasoned · {' · '.join([*parts, elapsed])}"

    def refresh_header(self) -> None:
        """Redraw the header line."""
        self._header.update(self.header_text)

    async def add_step(self) -> ThoughtStep:
        """Open a new thought at the end of the group."""
        step = ThoughtStep(len(self.steps) + 1)
        self.steps.append(step)
        await self._body.mount(step)
        self.refresh_header()
        return step

    async def add_tool(self, line: ToolCallLine) -> None:
        """Add a tool call below the thought that requested it."""
        self.tool_count += 1
        await self._body.mount(line)
        self.refresh_header()

    def set_expanded(self, *, expanded: bool) -> None:
        """Show the full thoughts, or fold the group back."""
        self.expanded = expanded
        self._sync()
        self.refresh_header()

    def toggle(self) -> None:
        """Flip between expanded and collapsed."""
        self.set_expanded(expanded=not self.expanded)

    async def finish(self) -> None:
        """Close the group and collapse it to its summary."""
        if not self.live:
            return
        for step in self.steps:
            await step.finish()
        self.live = False
        self._t1 = time.monotonic()
        if self._timer is not None:
            self._timer.stop()
        self.set_expanded(expanded=False)

    def _tick(self) -> None:
        self._frame += 1
        self.refresh_header()
        for step in self.steps:
            if step.streaming:
                step.refresh_title()

    def _sync(self) -> None:
        """Mirror the state in CSS classes, which decide what is visible."""
        self.set_class(self.live, "-live")
        self.set_class(self.expanded, "-full")
        self.set_class(not (self.live or self.expanded), "-collapsed")
