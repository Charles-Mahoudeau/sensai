"""Save the engine's conversation to a session store."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Protocol

from sensai.core.events import Done
from sensai.core.ports import StorageError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.engine import Engine
    from sensai.core.models import Message
    from sensai.core.ports import SessionRepository
    from sensai.core.usage import UsageMeter


_logger = logging.getLogger("SessionRecorder")


class Titler(Protocol):
    """Names a conversation from its first exchange, like `SessionTitler`."""

    async def title_for(self, user_message: str, reply: str) -> str | None:
        """Return a short title, or None if there is none."""
        ...


class SessionRecorder:
    """Save the messages and token usage of an engine, and switch sessions.

    Without a session to start from, one is created when the first message is
    saved. Clearing the conversation leaves the next session to be created the
    same way, so a session never starts empty. `watch` saves after every turn and
    titles the session once it has a first exchange.
    """

    def __init__(
        self,
        repo: SessionRepository,
        engine: Engine,
        *,
        model: str,
        session_id: int | None,
        saved: int,
        meter: UsageMeter | None = None,
        titler: Titler | None = None,
    ) -> None:
        """Record into an existing session, or into a new one if `session_id` is None.

        Args:
            repo: Where sessions and messages are stored.
            engine: The engine whose history is saved.
            model: The model recorded on sessions created by the recorder.
            session_id: The session to append to, or None to create one when needed.
            saved: How many messages of the engine history are already saved.
            meter: Counts the session's token usage; usage is not saved if None.
            titler: Names each session after its first exchange; sessions stay
                untitled if None.
        """
        self._repo = repo
        self._engine = engine
        self._model = model
        self._session_id = session_id
        self._saved = saved
        self._meter = meter
        self._titler = titler
        self._titled = False
        self._lock = asyncio.Lock()

    async def watch(self) -> None:
        """Save the conversation after every turn, and title the session.

        Runs until cancelled. Subscribe happens when the call starts, so create
        the task before the first message is submitted. A failure to save or to
        title is logged: it must not stop the watching.
        """
        async for event in self._engine.subscribe():
            if isinstance(event, Done):
                try:
                    await self._after_turn()
                except StorageError as error:
                    _logger.warning("Could not save the session: %s", error)

    async def _after_turn(self) -> None:
        await self.save()
        if self._titler is None or self._titled or self._session_id is None:
            return
        history = self._engine.history
        user = next((m.content for m in history if m.role == "user"), "")
        reply = next((m.content for m in history if m.role == "assistant"), "")
        if not user or not reply:
            return
        session_id = self._session_id
        self._titled = True
        title = await self._titler.title_for(user, reply)
        if title is None:
            # Try again after the next turn, unless the session has changed.
            if self._session_id == session_id:
                self._titled = False
            return
        await self._repo.set_title(session_id, title)

    async def save(self) -> None:
        """Append the messages and the usage not saved yet to the current session.

        Usage counted before any session exists waits for the first message.

        Raises:
            StorageError: The store failed to write.
        """
        async with self._lock:
            await self._save()

    async def _save(self) -> None:
        unsaved = self._engine.history[self._saved :]
        if unsaved and self._session_id is None:
            session = await self._repo.create_session(model=self._model)
            self._session_id = session.id
        if self._session_id is None:
            return
        for message in unsaved:
            await self._repo.append_message(self._session_id, message)
            self._saved += 1
        if self._meter is not None:
            await self._save_usage(self._meter, self._session_id)

    async def _save_usage(self, meter: UsageMeter, session_id: int) -> None:
        usage = meter.take_unsaved()
        if not usage.calls:
            return
        try:
            await self._repo.add_usage(session_id, usage)
        except BaseException:
            meter.restore_unsaved(usage)
            raise

    async def resume(self, session_id: int) -> Sequence[Message]:
        """Save the current session, then record into a stored one.

        Returns the messages of that session, for the caller to load into the
        engine right away: the next save appends what follows them.

        Raises:
            SessionNotFoundError: No session has this id.
            StorageError: The store failed to read or write.
        """
        async with self._lock:
            await self._save()
            session = await self._repo.get_session(session_id)
            messages = await self._repo.get_messages(session_id)
            self._session_id = session_id
            self._saved = len(messages)
            self._titled = session.title is not None
            if self._meter is not None:
                self._meter.reset(session.usage)
            return messages

    async def start_new(self) -> None:
        """Save the current session, then record into a new one.

        The new session is created when its first message is saved, so empty
        sessions are never stored. Call it right before clearing the engine
        history.

        Raises:
            StorageError: The store failed to write.
        """
        async with self._lock:
            await self._save()
            if self._session_id is None:
                return
            self._session_id = None
            self._saved = 0
            self._titled = False
            if self._meter is not None:
                self._meter.reset()
