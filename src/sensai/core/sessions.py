"""Save the engine's conversation to a session store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensai.core.engine import Engine
    from sensai.core.ports import SessionRepository


class SessionRecorder:
    """Save the messages of an engine to the current session, and switch sessions.

    Without a session to start from, one is created when the first message is
    saved. Clearing the conversation creates the next session right away.
    """

    def __init__(
        self,
        repo: SessionRepository,
        engine: Engine,
        *,
        model: str,
        session_id: int | None,
        saved: int,
    ) -> None:
        """Record into an existing session, or into a new one if `session_id` is None.

        Args:
            repo: Where sessions and messages are stored.
            engine: The engine whose history is saved.
            model: The model recorded on sessions created by the recorder.
            session_id: The session to append to, or None to create one when needed.
            saved: How many messages of the engine history are already saved.
        """
        self._repo = repo
        self._engine = engine
        self._model = model
        self._session_id = session_id
        self._saved = saved

    async def save(self) -> None:
        """Append the messages not saved yet to the current session.

        Raises:
            StorageError: The store failed to write.
        """
        unsaved = self._engine.history[self._saved :]
        if not unsaved:
            return
        if self._session_id is None:
            session = await self._repo.create_session(model=self._model)
            self._session_id = session.id
        for message in unsaved:
            await self._repo.append_message(self._session_id, message)
            self._saved += 1

    async def start_new(self) -> None:
        """Save the current session, then record into a new, empty one.

        The new session is created right away, so it is the latest one and a
        restart resumes it rather than the cleared conversation. A current
        session that is still empty is kept instead of creating another one.
        Call it right before clearing the engine history.

        Raises:
            StorageError: The store failed to write.
        """
        await self.save()
        if self._session_id is not None and self._saved == 0:
            return
        session = await self._repo.create_session(model=self._model)
        self._session_id = session.id
        self._saved = 0
