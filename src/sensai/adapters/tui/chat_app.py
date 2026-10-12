"""Terminal chat front-end built on Textual."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static

from sensai.adapters.tui.widgets import (
    AssistantMessage,
    EffortLabel,
    ErrorMessage,
    HintMessage,
    ReasoningGroup,
    ThoughtStep,
    ToolCallLine,
    UserMessage,
)
from sensai.core.events import (
    Done,
    ErrorEvent,
    MessageCompleted,
    MessageStarted,
    ThinkingGenerated,
    TokenGenerated,
    ToolRunFinished,
    ToolRunStarted,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from textual.app import ComposeResult
    from textual.binding import BindingType
    from textual.widget import Widget

    from sensai.core.engine import Engine
    from sensai.core.events import Event
    from sensai.core.models import ToolCall

EXIT_COMMANDS = frozenset({"/exit", "/quit"})
EMPTY_INPUT_HINT = "Type a message and press Enter. /exit to quit."


class SensaiApp(App[None]):
    """Chat with the engine: a transcript, a prompt and a status line."""

    TITLE = "Sensai"
    CSS_PATH = "sensai.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "interrupt", "Stop generating", show=False),
        Binding("ctrl+t", "toggle_thoughts", "Toggle thoughts", show=False),
        Binding("ctrl+r", "cycle_thinking_effort", "Thinking effort", show=False),
    ]

    def __init__(self, engine: Engine, model: str) -> None:
        """Create the app for an already-built engine.

        Args:
            engine: The engine to submit messages to and read events from.
            model: The model name, shown in the status line.
        """
        super().__init__()
        self._engine = engine
        self._model = model
        self._events: AsyncGenerator[Event] | None = None
        self._submission: str | None = None
        self._reply: AssistantMessage | None = None
        self._group: ReasoningGroup | None = None
        self._step: ThoughtStep | None = None
        self._streamed = False
        self._running_tools: list[tuple[ToolCall, ToolCallLine]] = []
        self._interrupted = False

    def compose(self) -> ComposeResult:
        """Lay out the transcript, the prompt and the status line."""
        yield VerticalScroll(id="transcript")
        yield Input(placeholder="Type a message…", id="prompt")
        with Horizontal(id="statusbar"):
            yield Static(id="status", markup=False)
            yield EffortLabel(self._engine.thinking_effort)

    def on_mount(self) -> None:
        """Subscribe to the engine before anything can be submitted."""
        self._events = self._engine.subscribe()
        self.run_worker(self._consume_events(self._events), name="engine-events")
        self.query_one("#transcript", VerticalScroll).anchor()
        self._set_status("ready")
        self.query_one(EffortLabel).set_effort(self._engine.thinking_effort)
        self.query_one("#prompt", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send the typed message, or handle an empty input or a command."""
        text = event.value.strip()
        event.input.clear()
        if not text:
            await self._write(HintMessage(EMPTY_INPUT_HINT))
            return
        if text in EXIT_COMMANDS:
            self.exit()
            return
        await self._write(UserMessage(text))
        self._submission = self._engine.submit(text)
        self._interrupted = False
        self._streamed = False
        event.input.disabled = True
        self._set_status("generating…")

    def action_interrupt(self) -> None:
        """Stop the answer being generated, if any."""
        if self._submission is not None and not self._interrupted:
            self._interrupted = True
            self._engine.interrupt(self._submission)

    def action_cycle_thinking_effort(self) -> None:
        """Switch to the next thinking effort; a running turn keeps its own."""
        effort = self._engine.cycle_thinking_effort()
        self.query_one(EffortLabel).set_effort(effort)

    def action_toggle_thoughts(self) -> None:
        """Expand every reasoning group, or collapse them if all are expanded."""
        groups = list(self.query(ReasoningGroup))
        expand = not all(group.expanded for group in groups)
        for group in groups:
            group.set_expanded(expanded=expand)

    async def _consume_events(self, events: AsyncGenerator[Event]) -> None:
        try:
            async for event in events:
                if event.submission_id == self._submission:
                    await self._render(event)
        finally:
            await events.aclose()

    async def _render(self, event: Event) -> None:
        match event:
            case MessageStarted():
                pass  # the answer is mounted lazily, below any tool call
            case ThinkingGenerated(text=text, ready=ready):
                await self._finish_reply()
                if self._step is None:
                    group = await self._open_group()
                    self._step = await group.add_step()
                self._step.add_fragment(text)
                if ready:
                    self._step.mark_ready()
            case TokenGenerated(text=text):
                self._streamed = True
                await self._close_reasoning()
                if self._reply is None:
                    self._reply = AssistantMessage()
                    await self._write(self._reply)
                await self._reply.add_fragment(text)
            case ToolRunStarted(call=call):
                await self._end_step()
                await self._finish_reply()
                line = ToolCallLine(call.name)
                self._running_tools.append((call, line))
                await (await self._open_group()).add_tool(line)
            case ToolRunFinished(call=call, result=result):
                self._finish_tool(call, result.content, is_error=result.is_error)
            case MessageCompleted(message=message):
                if not self._streamed and message.content:
                    self._reply = AssistantMessage()
                    await self._write(self._reply)
                    await self._reply.add_fragment(message.content)
                await self._finish_reply()
            case ErrorEvent(error=error):
                await self._close_reasoning()
                await self._drop_empty_reply()
                await self._write(ErrorMessage(str(error) or type(error).__name__))
            case Done():
                await self._finish_reply()
                for _, line in self._running_tools:
                    line.interrupt()
                self._running_tools.clear()
                await self._close_reasoning()
                if self._interrupted:
                    await self._write(HintMessage("(interrupted)"))
                self._submission = None
                prompt = self.query_one("#prompt", Input)
                prompt.disabled = False
                prompt.focus()
                self._set_status("ready")

    def _finish_tool(self, call: ToolCall, content: str, *, is_error: bool) -> None:
        for index, (started, line) in enumerate(self._running_tools):
            if started is call or started == call:
                line.finish(content, is_error=is_error)
                del self._running_tools[index]
                return

    async def _open_group(self) -> ReasoningGroup:
        if self._group is None:
            self._group = ReasoningGroup()
            await self._write(self._group)
        return self._group

    async def _end_step(self) -> None:
        if self._step is not None:
            await self._step.finish()
            self._step = None

    async def _close_reasoning(self) -> None:
        """Collapse the reasoning group, once the answer or the turn is over."""
        await self._end_step()
        if self._group is not None:
            await self._group.finish()
            self._group = None

    async def _finish_reply(self) -> None:
        if self._reply is not None:
            await self._reply.finish()
        await self._drop_empty_reply()
        self._reply = None

    async def _drop_empty_reply(self) -> None:
        if self._reply is not None and not self._reply.text:
            await self._reply.finish()
            await self._reply.remove()
            self._reply = None

    async def _write(self, widget: Widget) -> None:
        await self.query_one("#transcript", VerticalScroll).mount(widget)

    def _set_status(self, state: str) -> None:
        hints = "esc stop · ctrl+t thoughts · ctrl+r effort · ctrl+q quit"
        self.query_one("#status", Static).update(f"{self._model} · {state}   {hints}")
