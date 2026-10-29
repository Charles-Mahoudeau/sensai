"""The /sessions panel: every stored session with its title and last activity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.content import Content
from textual.widgets import Static

from sensai.adapters.tui.panels.base import Panel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual.app import ComposeResult

    from sensai.core.models.memory import Session

EMPTY_TEXT = "No sessions yet"
UNTITLED = "Untitled"
HINTS = "↑↓ scroll · esc close"


class SessionsPanel(Panel):
    """List the sessions, the most recently active first."""

    def __init__(self, sessions: Sequence[Session]) -> None:
        """Show `sessions` in the order given."""
        super().__init__(id="sessions-panel", classes="panel")
        self._sessions = tuple(sessions)

    def compose(self) -> ComposeResult:
        """Lay out one row per session; the count and hints go in the border."""
        self.border_title = Content(f"Sessions · {len(self._sessions)}")
        self.border_subtitle = HINTS
        if not self._sessions:
            yield Static(EMPTY_TEXT, classes="panel-empty", markup=False)
        for session in self._sessions:
            yield Static(_row(session), classes="session-row")


def _row(session: Session) -> Content:
    """The date of the last activity, then the title or a placeholder."""
    when = session.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
    title = (session.title, "bold") if session.title else (UNTITLED, "dim italic")
    return Content.assemble((when, "dim"), "  ", title)
