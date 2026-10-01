"""SQLite implementation of the `SessionStore` port."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sensai.adapters.storage.sqlite import SqliteDatabase, from_db_time
from sensai.core.models.llm import Message
from sensai.core.models.memory import Session
from sensai.core.models.tools import ToolCall
from sensai.core.ports import SessionNotFoundError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_SESSIONS_TABLE = "sessions"
_MESSAGES_TABLE = "messages"


def _tool_call_to_json(call: ToolCall) -> dict[str, Any]:
    """Encode a tool call in Ollama's `tool_calls` format."""
    encoded: dict[str, Any] = {
        "function": {"name": call.name, "arguments": dict(call.arguments)}
    }
    if call.id is not None:
        encoded["id"] = call.id
    return encoded


def _to_message_row(message: Message) -> tuple[Any, ...]:
    tool_calls_json = (
        json.dumps([_tool_call_to_json(c) for c in message.tool_calls])
        if message.tool_calls
        else None
    )
    return (
        message.role,
        message.content,
        message.reasoning_summary or None,
        tool_calls_json,
        message.tool_name,
    )


class SqliteSessionRepository:
    """Stores sessions, their messages and the user profile in SQLite."""

    def __init__(self, db: SqliteDatabase) -> None:
        """Read the tables' columns from the migrated schema.

        Args:
            db: The database instance.

        Raises:
            StorageError: A table does not exist (migrations not applied).
        """
        self._db = db
        self._session_column_names = db.columns(_SESSIONS_TABLE)
        self._session_columns = ", ".join(self._session_column_names)
        self._message_column_names = db.columns(_MESSAGES_TABLE)
        self._message_columns = ", ".join(self._message_column_names)

    def _to_session(self, row: Sequence[Any]) -> Session:
        fields = dict(zip(self._session_column_names, row, strict=True))
        return Session(
            fields["id"],
            fields["model"],
            from_db_time(fields["created_at"]),
            from_db_time(fields["updated_at"]),
            fields["title"],
        )

    def _to_message(self, row: Sequence[Any]) -> Message:
        fields = dict(zip(self._message_column_names, row, strict=True))
        tool_calls = tuple(
            ToolCall(c["function"]["name"], c["function"]["arguments"], c.get("id"))
            for c in json.loads(fields["tool_calls_json"] or "[]")
        )
        return Message(
            fields["role"],
            content=fields["content"],
            tool_calls=tool_calls,
            tool_name=fields["tool_name"],
            reasoning_summary=fields["thinking"] or "",
        )

    async def create_session(self, *, model: str, title: str | None = None) -> Session:
        """Insert an empty session."""

        def create() -> Session:
            now = self._db.now()
            with self._db.write() as conn:
                row = conn.execute(
                    "INSERT INTO sessions (model, title, created_at, updated_at)"
                    f" VALUES (?, ?, ?, ?) RETURNING {self._session_columns}",
                    (model, title, now, now),
                ).fetchone()
                return self._to_session(row)

        return await self._db.run(create)

    async def get_session(self, session_id: int) -> Session:
        """Return a session or raise `SessionNotFoundError`."""
        return await self._db.run(lambda: self._get_session(session_id))

    def _get_session(self, session_id: int) -> Session:
        row = self._db.conn.execute(
            f"SELECT {self._session_columns} FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        return self._to_session(row)

    async def list_sessions(self, *, limit: int = 50) -> Sequence[Session]:
        """Return the most recently updated sessions first."""

        def list_() -> list[Session]:
            rows = self._db.conn.execute(
                f"SELECT {self._session_columns} FROM sessions"
                " ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._to_session(row) for row in rows]

        return await self._db.run(list_)

    async def append_message(self, session_id: int, message: Message) -> None:
        """Append a message after the session's last one and refresh its time."""

        def append() -> None:
            now = self._db.now()
            with self._db.write() as conn:
                touched = conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                ).rowcount
                if not touched:
                    raise SessionNotFoundError(session_id)
                conn.execute(
                    "INSERT INTO messages (session_id, parent_id, role, content,"
                    " thinking, tool_calls_json, tool_name, created_at) VALUES"
                    " (?, (SELECT max(id) FROM messages WHERE session_id = ?),"
                    " ?, ?, ?, ?, ?, ?)",
                    (session_id, session_id, *_to_message_row(message), now),
                )

        await self._db.run(append)

    async def get_messages(self, session_id: int) -> Sequence[Message]:
        """Return the messages of a session, oldest first."""

        def get() -> list[Message]:
            self._get_session(session_id)
            rows = self._db.conn.execute(
                f"SELECT {self._message_columns} FROM messages"
                " WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return [self._to_message(row) for row in rows]

        return await self._db.run(get)

    async def delete_session(self, session_id: int) -> None:
        """Delete a session; its messages go with it (`ON DELETE CASCADE`)."""

        def delete() -> None:
            with self._db.write() as conn:
                deleted = conn.execute(
                    "DELETE FROM sessions WHERE id = ?", (session_id,)
                ).rowcount
                if not deleted:
                    raise SessionNotFoundError(session_id)

        await self._db.run(delete)
