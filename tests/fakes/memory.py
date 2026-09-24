"""Fakes implementing the session and memory ports."""

from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sensai.core.models.memory import MemoryRecord, Session
from sensai.core.ports import (
    DuplicateMemoryError,
    MemoryNotFoundError,
    SessionNotFoundError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sensai.core.models.llm import Message
    from sensai.core.ports import MemoryStore, SessionStore


def _ticking_clock() -> Callable[[], datetime]:
    """Return a clock that advances one second per call, so order is testable."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    counter = itertools.count()
    return lambda: start + timedelta(seconds=next(counter))


class InMemorySessionStore:
    """Keeps sessions, messages and the profile in dicts."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        """Start empty; `clock` supplies timestamps (deterministic by default)."""
        self._clock = clock or _ticking_clock()
        self._ids = itertools.count(1)
        self._sessions: dict[int, Session] = {}
        self._messages: dict[int, list[Message]] = {}
        self._profile: dict[str, str] = {}

    async def create_session(self, *, model: str, title: str | None = None) -> Session:
        """Create an empty session."""
        now = self._clock()
        session = Session(next(self._ids), model, now, now, title)
        self._sessions[session.id] = session
        self._messages[session.id] = []
        return session

    async def get_session(self, session_id: int) -> Session:
        """Return a session or raise `SessionNotFoundError`."""
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFoundError(session_id) from None

    async def list_sessions(self, *, limit: int = 50) -> Sequence[Session]:
        """Return the most recently updated sessions first."""
        ordered = sorted(
            self._sessions.values(), key=lambda s: s.updated_at, reverse=True
        )
        return ordered[:limit]

    async def append_message(self, session_id: int, message: Message) -> None:
        """Append a message and refresh the session's update time."""
        session = await self.get_session(session_id)
        self._messages[session_id].append(message)
        self._sessions[session_id] = replace(session, updated_at=self._clock())

    async def get_messages(self, session_id: int) -> Sequence[Message]:
        """Return the messages of a session, oldest first."""
        await self.get_session(session_id)
        return list(self._messages[session_id])

    async def delete_session(self, session_id: int) -> None:
        """Delete a session and its messages."""
        await self.get_session(session_id)
        del self._sessions[session_id]
        del self._messages[session_id]

    async def get_profile(self) -> Mapping[str, str]:
        """Return a copy of the profile."""
        return dict(self._profile)

    async def set_profile_value(self, key: str, value: str) -> None:
        """Create or replace a profile entry."""
        self._profile[key] = value

    async def delete_profile_value(self, key: str) -> None:
        """Remove a profile entry if it exists."""
        self._profile.pop(key, None)


class InMemoryMemoryStore:
    """Keeps long-term memory records in a dict."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        """Start empty; `clock` supplies timestamps (deterministic by default)."""
        self._clock = clock or _ticking_clock()
        self._ids = itertools.count(1)
        self._records: dict[int, MemoryRecord] = {}

    def _check_unique(self, name: str, type_: str, *, ignore_id: int = 0) -> None:
        for record in self._records.values():
            if record.id != ignore_id and (record.name, record.type) == (name, type_):
                raise DuplicateMemoryError(f"{type_}/{name}")

    async def create(
        self, *, name: str, type: str, description: str | None = None
    ) -> MemoryRecord:
        """Create a record, refusing a duplicate name and type."""
        self._check_unique(name, type)
        now = self._clock()
        record = MemoryRecord(next(self._ids), name, type, now, now, description)
        self._records[record.id] = record
        return record

    async def get(self, memory_id: int) -> MemoryRecord:
        """Return a record or raise `MemoryNotFoundError`."""
        try:
            return self._records[memory_id]
        except KeyError:
            raise MemoryNotFoundError(memory_id) from None

    async def find(
        self, *, type: str | None = None, query: str | None = None
    ) -> Sequence[MemoryRecord]:
        """Return matching records, most recently updated first."""
        needle = query.lower() if query else None
        matches = [
            record
            for record in self._records.values()
            if (type is None or record.type == type)
            and (
                needle is None
                or needle in record.name.lower()
                or needle in (record.description or "").lower()
            )
        ]
        return sorted(matches, key=lambda r: r.updated_at, reverse=True)

    async def update(
        self,
        memory_id: int,
        *,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
    ) -> MemoryRecord:
        """Change the given fields; `None` keeps the current value."""
        current = await self.get(memory_id)
        new_name = current.name if name is None else name
        new_type = current.type if type is None else type
        self._check_unique(new_name, new_type, ignore_id=memory_id)
        updated = replace(
            current,
            name=new_name,
            type=new_type,
            description=current.description if description is None else description,
            updated_at=self._clock(),
        )
        self._records[memory_id] = updated
        return updated

    async def delete(self, memory_id: int) -> None:
        """Delete a record or raise `MemoryNotFoundError`."""
        await self.get(memory_id)
        del self._records[memory_id]


if TYPE_CHECKING:

    def _session_conforms(fake: InMemorySessionStore) -> SessionStore:
        return fake

    def _memory_conforms(fake: InMemoryMemoryStore) -> MemoryStore:
        return fake
