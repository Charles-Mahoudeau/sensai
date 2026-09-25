"""SQLite implementation of the `SessionStore` port."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sensai.adapters.memory._sqlite import SqliteStore, from_db_time
from sensai.core.models.llm import Message
from sensai.core.models.memory import Session
from sensai.core.models.tools import ToolCall
from sensai.core.ports import SessionNotFoundError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sensai.core.ports import SessionStore

_SESSION_COLUMNS = "id, model, created_at, updated_at, title"
_MESSAGE_COLUMNS = "role, content, thinking, tool_calls_json, tool_name"


def _to_session(row: Sequence[Any]) -> Session:
    id_, model, created_at, updated_at, title = row
    return Session(
        id_, model, from_db_time(created_at), from_db_time(updated_at), title
    )


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


def _to_message(row: Sequence[Any]) -> Message:
    role, content, thinking, tool_calls_json, tool_name = row
    tool_calls = tuple(
        ToolCall(c["function"]["name"], c["function"]["arguments"], c.get("id"))
        for c in json.loads(tool_calls_json or "[]")
    )
    return Message(
        role,
        content=content,
        tool_calls=tool_calls,
        tool_name=tool_name,
        reasoning_summary=thinking or "",
    )


class SqliteSessionStore(SqliteStore):
    """Stores sessions, their messages and the user profile in SQLite."""

    async def create_session(self, *, model: str, title: str | None = None) -> Session:
        """Insert an empty session."""

        def create() -> Session:
            now = self._now()
            with self._write() as conn:
                row = conn.execute(
                    "INSERT INTO sessions (model, title, created_at, updated_at)"
                    f" VALUES (?, ?, ?, ?) RETURNING {_SESSION_COLUMNS}",
                    (model, title, now, now),
                ).fetchone()
                return _to_session(row)

        return await self._run(create)

    async def get_session(self, session_id: int) -> Session:
        """Return a session or raise `SessionNotFoundError`."""
        return await self._run(lambda: self._get_session(session_id))

    def _get_session(self, session_id: int) -> Session:
        row = self._conn.execute(
            f"SELECT {_SESSION_COLUMNS} FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        return _to_session(row)

    async def list_sessions(self, *, limit: int = 50) -> Sequence[Session]:
        """Return the most recently updated sessions first."""

        def list_() -> list[Session]:
            rows = self._conn.execute(
                f"SELECT {_SESSION_COLUMNS} FROM sessions"
                " ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_to_session(row) for row in rows]

        return await self._run(list_)

    async def append_message(self, session_id: int, message: Message) -> None:
        """Append a message after the session's last one and refresh its time."""

        def append() -> None:
            now = self._now()
            with self._write() as conn:
                touched = conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                ).rowcount
                if not touched:
                    raise SessionNotFoundError(session_id)
                conn.execute(
                    f"INSERT INTO messages (session_id, parent_id, {_MESSAGE_COLUMNS},"
                    " created_at) VALUES"
                    " (?, (SELECT max(id) FROM messages WHERE session_id = ?),"
                    " ?, ?, ?, ?, ?, ?)",
                    (session_id, session_id, *_to_message_row(message), now),
                )

        await self._run(append)

    async def get_messages(self, session_id: int) -> Sequence[Message]:
        """Return the messages of a session, oldest first."""

        def get() -> list[Message]:
            self._get_session(session_id)
            rows = self._conn.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages"
                " WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return [_to_message(row) for row in rows]

        return await self._run(get)

    async def delete_session(self, session_id: int) -> None:
        """Delete a session; its messages go with it (`ON DELETE CASCADE`)."""

        def delete() -> None:
            with self._write() as conn:
                deleted = conn.execute(
                    "DELETE FROM sessions WHERE id = ?", (session_id,)
                ).rowcount
                if not deleted:
                    raise SessionNotFoundError(session_id)

        await self._run(delete)

    async def get_profile(self) -> Mapping[str, str]:
        """Return the whole profile."""

        def get() -> dict[str, str]:
            rows = self._conn.execute("SELECT key, value FROM user_profile")
            return dict(rows.fetchall())

        return await self._run(get)

    async def set_profile_value(self, key: str, value: str) -> None:
        """Create or replace a profile entry."""

        def set_() -> None:
            with self._write() as conn:
                conn.execute(
                    "INSERT INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)"
                    " ON CONFLICT (key) DO UPDATE"
                    " SET value = excluded.value, updated_at = excluded.updated_at",
                    (key, value, self._now()),
                )

        await self._run(set_)

    async def delete_profile_value(self, key: str) -> None:
        """Remove a profile entry if it exists."""

        def delete() -> None:
            with self._write() as conn:
                conn.execute("DELETE FROM user_profile WHERE key = ?", (key,))

        await self._run(delete)


if TYPE_CHECKING:

    def _conforms(store: SqliteSessionStore) -> SessionStore:
        return store
