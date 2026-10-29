"""The /sessions panel: every stored session, to pick one to resume."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.content import Content
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sensai.adapters.tui.panels.base import Panel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from sensai.core.models.memory import Session

EMPTY_TEXT = "No sessions yet"
UNTITLED = "Untitled"
HINTS = "↑↓ move · enter resume · esc close"
LIST_HINTS = "↑↓ move · esc close"

type SelectSession = Callable[[Session], Awaitable[None]]


class SessionList(OptionList):
    """The sessions, most recently active first; the panel keeps the focus rules."""


class SessionsPanel(Panel):
    """List the sessions and resume the one chosen.

    Without a `on_select` callback the list is read-only.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Previous session", show=False),
        Binding("down", "move(1)", "Next session", show=False),
    ]

    def __init__(
        self, sessions: Sequence[Session], on_select: SelectSession | None = None
    ) -> None:
        """Show `sessions` in the order given.

        Args:
            sessions: The sessions to list.
            on_select: Awaited with the session chosen, before the panel closes.
        """
        super().__init__(id="sessions-panel", classes="panel")
        self._sessions = tuple(sessions)
        self._on_select = on_select

    def compose(self) -> ComposeResult:
        """Lay out the list; the count and hints go in the border."""
        self.border_title = Content(f"Sessions · {len(self._sessions)}")
        self.border_subtitle = HINTS if self._on_select else LIST_HINTS
        if not self._sessions:
            yield Static(EMPTY_TEXT, classes="panel-empty", markup=False)
            return
        yield SessionList(
            *(
                Option(_row(session), id=str(index))
                for index, session in enumerate(self._sessions)
            ),
            id="sessions-list",
        )

    def focus_first(self) -> None:
        """Focus the list, so the arrows and enter act on it."""
        for sessions in self.query(SessionList):
            sessions.focus()
            return
        super().focus_first()

    def action_move(self, step: int) -> None:
        """Highlight the previous or next session."""
        for sessions in self.query(SessionList):
            if step < 0:
                sessions.action_cursor_up()
            else:
                sessions.action_cursor_down()

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Resume the session chosen, then close the panel."""
        event.stop()
        if self._on_select is None or event.option.id is None:
            return
        await self._on_select(self._sessions[int(event.option.id)])
        self.action_close()


def _row(session: Session) -> Content:
    """The date of the last activity, then the title or a placeholder."""
    when = session.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
    title = (session.title, "bold") if session.title else (UNTITLED, "dim italic")
    return Content.assemble((when, "dim"), "  ", title)
