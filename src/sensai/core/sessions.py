"""Save the engine's conversation to a session store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensai.core.engine import Engine
    from sensai.core.ports import SessionRepository
    from sensai.core.usage import UsageMeter


class SessionRecorder:
    """Save the messages and token usage of an engine, and switch sessions.

    Without a session to start from, one is created when the first message is
    saved. Clearing the conversation leaves the next session to be created the
    same way, so a session never starts empty.
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
    ) -> None:
        """Record into an existing session, or into a new one if `session_id` is None.

        Args:
            repo: Where sessions and messages are stored.
            engine: The engine whose history is saved.
            model: The model recorded on sessions created by the recorder.
            session_id: The session to append to, or None to create one when needed.
            saved: How many messages of the engine history are already saved.
            meter: Counts the session's token usage; usage is not saved if None.
        """
        self._repo = repo
        self._engine = engine
        self._model = model
        self._session_id = session_id
        self._saved = saved
        self._meter = meter

    async def save(self) -> None:
        """Append the messages and the usage not saved yet to the current session.

        Usage counted before any session exists waits for the first message.

        Raises:
            StorageError: The store failed to write.
        """
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

    async def start_new(self) -> None:
        """Save the current session, then record into a new one.

        The new session is created when its first message is saved, so empty
        sessions are never stored. Call it right before clearing the engine
        history.

        Raises:
            StorageError: The store failed to write.
        """
        await self.save()
        if self._session_id is None:
            return
        self._session_id = None
        self._saved = 0
        if self._meter is not None:
            self._meter.reset()
