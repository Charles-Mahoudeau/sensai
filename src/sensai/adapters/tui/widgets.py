"""Widgets rendering the chat transcript."""

from __future__ import annotations

import textwrap
import time
from typing import TYPE_CHECKING

from textual.color import Color
from textual.containers import Vertical
from textual.content import Content
from textual.widgets import Markdown, Static

if TYPE_CHECKING:
    from typing import Literal

    from textual.app import ComposeResult
    from textual.timer import Timer
    from textual.widgets.markdown import MarkdownStream

    from sensai.core.models import ThinkingEffort


class UserMessage(Static):
    """A message typed by the user."""

    DEFAULT_CSS = """
    UserMessage {
        color: $text-muted;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, text: str) -> None:
        """Render the user's text after a prompt marker."""
        super().__init__(f"> {text}", markup=False)
        self.text = text


class AssistantMessage(Markdown):
    """A model answer, rendered as Markdown while it streams in."""

    DEFAULT_CSS = """
    AssistantMessage {
        margin: 1 0 0 0;
        padding: 0;
        background: transparent;
    }
    """

    def __init__(self) -> None:
        """Start with an empty document."""
        super().__init__()
        self.text = ""
        self._stream: MarkdownStream | None = None

    async def add_fragment(self, fragment: str) -> None:
        """Append a streamed fragment to the answer."""
        if self._stream is None:
            self._stream = Markdown.get_stream(self)
        self.text += fragment
        await self._stream.write(fragment)

    async def finish(self) -> None:
        """Flush the remaining fragments and stop streaming."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None


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
        self._summary_line.update(_trim(self.text, self.SUMMARY_LIMIT))
        await self._full_text.update(self.text)

    def _tail(self) -> str:
        """The last lines of the thought, wrapped to the current width."""
        width = max(20, self.size.width - 4 if self.size.width else 80)
        lines = textwrap.wrap(" ".join(self.text.split()), width=width)
        tail = lines[-self.LIVE_LINES :]
        if len(lines) > len(tail):
            tail[0] = "…" + tail[0]
        return "\n".join(tail)


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


class ToolCallLine(Static):
    """One tool call: "Calling tool …" while it runs, then its trimmed result."""

    DEFAULT_CSS = """
    ToolCallLine {
        color: $text-muted;
    }
    """

    RESULT_LIMIT = 80

    def __init__(self, name: str) -> None:
        """Start in the running state."""
        super().__init__(_running(name))
        self.tool_name = name
        self.text = f"● Calling tool {name}..."
        self.state: Literal["running", "done", "failed", "interrupted"] = "running"

    def finish(self, content: str, *, is_error: bool = False) -> None:
        """Replace the running line by the trimmed result of the call."""
        summary = _trim(content, self.RESULT_LIMIT)
        if is_error:
            self.state = "failed"
            self.text = f"● Failed to call tool {self.tool_name}: {summary}"
            self.update(
                Content.assemble(
                    ("● Failed to call tool ", "$error"),
                    (self.tool_name, "$accent"),
                    (f": {summary}", "$error"),
                )
            )
        else:
            self.state = "done"
            self.text = f"● Called tool {self.tool_name}: {summary}"
            self.update(
                Content.assemble(
                    ("●", "$success"),
                    " Called tool ",
                    (self.tool_name, "$accent"),
                    f": {summary}",
                )
            )

    def interrupt(self) -> None:
        """Mark a call that never reported a result, e.g. after an interrupt."""
        self.state = "interrupted"
        self.text = f"● Interrupted tool {self.tool_name}…"
        self.update(
            Content.assemble("● Interrupted tool ", (self.tool_name, "$accent"), "…")
        )


def _running(name: str) -> Content:
    return Content.assemble("● Calling tool ", (name, "$accent"), "...")


def _trim(text: str, limit: int) -> str:
    """Collapse whitespace into a single line and cut it at ``limit`` characters."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


class ErrorMessage(Static):
    """An error reported by the engine."""

    DEFAULT_CSS = """
    ErrorMessage {
        color: $error;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, text: str) -> None:
        """Render the error text."""
        super().__init__(f"✗ error: {text}", markup=False)
        self.text = text


class HintMessage(Static):
    """A short, dim hint about how to use the prompt."""

    DEFAULT_CSS = """
    HintMessage {
        color: $text-disabled;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, text: str) -> None:
        """Render the hint text."""
        super().__init__(text, markup=False)
        self.text = text


NO_THINKING_COLOR = "#ff8a65"
RAINBOW_INTERVAL = 0.08
RAINBOW_HUE_STEP = 0.07
RAINBOW_HUE_SPEED = 0.04


class EffortLabel(Static):
    """The thinking effort, right-aligned; Ultra is animated in rainbow colors."""

    DEFAULT_CSS = """
    EffortLabel {
        width: auto;
        padding: 0 3 0 0;
        color: $text-muted;
    }
    """

    def __init__(self, effort: ThinkingEffort) -> None:
        """Show the given effort."""
        super().__init__(id="effort", markup=False)
        self.effort = effort
        self._phase = 0.0
        self._rainbow_timer: Timer | None = None

    def set_effort(self, effort: ThinkingEffort) -> None:
        """Show another effort, animating it only when it is Ultra."""
        self.effort = effort
        self._stop_animation()
        if effort.name == "ULTRA":
            self._phase = 0.0
            self._rainbow_timer = self.set_interval(
                RAINBOW_INTERVAL, self._tick_rainbow
            )
            self._tick_rainbow()
        elif effort.name == "NONE":
            self.update(Content.assemble((effort.label, NO_THINKING_COLOR)))
        else:
            self.update(effort.label)

    def _tick_rainbow(self) -> None:
        self._phase = (self._phase + RAINBOW_HUE_SPEED) % 1.0
        label = self.effort.label
        self.update(
            Content.assemble(
                *(
                    (
                        char,
                        Color.from_hsl(
                            (self._phase + index * RAINBOW_HUE_STEP) % 1.0, 0.9, 0.6
                        ).hex,
                    )
                    for index, char in enumerate(label)
                )
            )
        )

    def _stop_animation(self) -> None:
        if self._rainbow_timer is not None:
            self._rainbow_timer.stop()
            self._rainbow_timer = None
