"""The /sessions command: list the stored sessions and resume one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.tui.commands.registry import CommandSpec
from sensai.adapters.tui.panels import SessionsPanel
from sensai.core.errors import SensaiError, SubmissionInProgressError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from sensai.adapters.tui.commands.registry import CommandContext, CommandRegistry
    from sensai.core.models import Message
    from sensai.core.models.memory import Session

UNTITLED = "Untitled session"


def register_self(
    registry: CommandRegistry,
    *,
    on_resume: Callable[[int], Awaitable[Sequence[Message]]] | None = None,
) -> None:
    """Register /sessions, and its alias /chats, into a command registry.

    Args:
        registry: The registry to add the command to.
        on_resume: Awaited with a session id to switch to that session; it
            returns the session's messages. Sessions can only be listed
            without it.
    """

    async def sessions(context: CommandContext, argument: str) -> None:
        del argument
        try:
            stored = await context.engine.list_sessions()
        except SensaiError as error:
            await context.show_hint(f"Could not read the sessions: {error}")
            return

        async def resume(session: Session) -> None:
            assert on_resume is not None
            if context.engine.busy:
                await context.show_hint(
                    "(cannot switch sessions while an answer is running)"
                )
                return
            try:
                messages = await on_resume(session.id)
                context.engine.restore(messages)
            except (SensaiError, SubmissionInProgressError) as error:
                await context.show_hint(f"Could not resume the session: {error}")
                return
            await context.show_session(session.title or UNTITLED, messages)

        await context.open_panel(
            SessionsPanel(stored, resume if on_resume is not None else None)
        )

    registry.register(
        CommandSpec("/sessions", "List and resume your sessions", aliases=("/chats",)),
        sessions,
    )
