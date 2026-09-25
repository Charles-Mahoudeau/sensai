"""Ports for persisted sessions, the user profile and long-term memory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.models.llm import Message
    from sensai.core.models.memory import MemoryRecord, Session


class StorageError(Exception):
    """Base class for every error raised by a session or memory store."""


class SessionNotFoundError(StorageError):
    """The requested session does not exist."""


class MemoryNotFoundError(StorageError):
    """The requested memory record does not exist."""


class DuplicateMemoryError(StorageError):
    """A memory record with the same name and type already exists."""


class SessionStore(Protocol):
    """Saves conversations and the persistent user profile."""

    async def create_session(self, *, model: str, title: str | None = None) -> Session:
        """Start a new, empty session.

        Args:
            model: The model the session talks to.
            title: An optional human-readable title.

        Raises:
            StorageError: The store failed to write.
        """
        ...

    async def get_session(self, session_id: int) -> Session:
        """Return one session.

        Raises:
            SessionNotFoundError: No session has this id.
            StorageError: The store failed to read.
        """
        ...

    async def list_sessions(self, *, limit: int = 50) -> Sequence[Session]:
        """Return the most recently updated sessions, newest first.

        Args:
            limit: The maximum number of sessions to return.

        Raises:
            StorageError: The store failed to read.
        """
        ...

    async def append_message(self, session_id: int, message: Message) -> None:
        """Add a message at the end of a session and refresh its update time.

        Raises:
            SessionNotFoundError: No session has this id.
            StorageError: The store failed to write.
        """
        ...

    async def get_messages(self, session_id: int) -> Sequence[Message]:
        """Return every message of a session, oldest first.

        Raises:
            SessionNotFoundError: No session has this id.
            StorageError: The store failed to read.
        """
        ...

    async def delete_session(self, session_id: int) -> None:
        """Delete a session and all its messages.

        Raises:
            SessionNotFoundError: No session has this id.
            StorageError: The store failed to write.
        """
        ...

    async def get_profile(self) -> Mapping[str, str]:
        """Return the user profile as key/value pairs (empty if none is set).

        Raises:
            StorageError: The store failed to read.
        """
        ...

    async def set_profile_value(self, key: str, value: str) -> None:
        """Create or replace one profile entry.

        Raises:
            StorageError: The store failed to write.
        """
        ...

    async def delete_profile_value(self, key: str) -> None:
        """Remove one profile entry; does nothing if the key is unknown.

        Raises:
            StorageError: The store failed to write.
        """
        ...


class MemoryStore(Protocol):
    """Long-term structured memory the agent drives through CRUD tool calls."""

    async def create(
        self, *, name: str, type: str, description: str | None = None
    ) -> MemoryRecord:
        """Create a memory record.

        Args:
            name: What the record is about, e.g. a person or a project.
            type: The kind of record, e.g. `person`, `project`, `concept`.
            description: Free-text details.

        Raises:
            DuplicateMemoryError: A record with this name and type exists.
            StorageError: The store failed to write.
        """
        ...

    async def get(self, memory_id: int) -> MemoryRecord:
        """Return one record.

        Raises:
            MemoryNotFoundError: No record has this id.
            StorageError: The store failed to read.
        """
        ...

    async def find(
        self, *, type: str | None = None, query: str | None = None
    ) -> Sequence[MemoryRecord]:
        """Search records, most recently updated first.

        Args:
            type: Only return records of this type; `None` matches every type.
            query: Only return records whose name or description contains this
                text, ignoring case; `None` matches every record.

        Raises:
            StorageError: The store failed to read.
        """
        ...

    async def update(
        self,
        memory_id: int,
        *,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
    ) -> MemoryRecord:
        """Change some fields of a record; a `None` argument keeps its value.

        To clear a description, pass an empty string.

        Raises:
            MemoryNotFoundError: No record has this id.
            DuplicateMemoryError: The new name and type collide with another
                record.
            StorageError: The store failed to write.
        """
        ...

    async def delete(self, memory_id: int) -> None:
        """Delete a record.

        Unlike `VectorStore.delete`, an unknown id is an error: the agent
        calls this with an id it chose, and needs to be told when it is wrong.

        Raises:
            MemoryNotFoundError: No record has this id.
            StorageError: The store failed to write.
        """
        ...
