"""Tests for the session recorder."""

from __future__ import annotations

import asyncio

import pytest

from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import Message
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import StorageError
from sensai.core.sessions import SessionRecorder
from tests.core.test_engine import ScriptedRunner
from tests.fakes import InMemorySessionStore


def _engine(history: tuple[Message, ...]) -> Engine:
    return Engine(ScriptedRunner(()), Pipeline(), EventBus(), history=history)


class _FlakyStore(InMemorySessionStore):
    """Fails the append of one message, once."""

    def __init__(self, fail_on: Message) -> None:
        super().__init__()
        self._fail_on: Message | None = fail_on

    async def append_message(self, session_id: int, message: Message) -> None:
        if message == self._fail_on:
            self._fail_on = None
            raise StorageError("disk full")
        await super().append_message(session_id, message)


def test_only_unsaved_messages_are_appended() -> None:
    """Messages restored from the session are not saved twice."""

    async def run() -> None:
        repo = InMemorySessionStore()
        session = await repo.create_session(model="m")
        old = Message.user("old")
        await repo.append_message(session.id, old)
        engine = _engine((old, Message.user("new")))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=session.id, saved=1
        )

        await recorder.save()
        await recorder.save()

        assert await repo.get_messages(session.id) == [old, Message.user("new")]

    asyncio.run(run())


def test_start_new_saves_then_records_into_a_new_session() -> None:
    """After start_new and a cleared engine, messages go to a fresh session."""

    async def run() -> None:
        repo = InMemorySessionStore()
        session = await repo.create_session(model="m")
        engine = _engine((Message.user("first"),))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=session.id, saved=0
        )

        await recorder.start_new()
        engine.clear()
        engine._history.append(Message.user("second"))
        await recorder.save()

        sessions = await repo.list_sessions()
        assert len(sessions) == 2
        assert await repo.get_messages(session.id) == [Message.user("first")]
        assert await repo.get_messages(sessions[0].id) == [Message.user("second")]

    asyncio.run(run())


def test_no_session_is_created_when_there_is_nothing_to_save() -> None:
    """Clearing then quitting does not leave an empty session behind."""

    async def run() -> None:
        repo = InMemorySessionStore()
        recorder = SessionRecorder(
            repo, _engine(()), model="m", session_id=None, saved=0
        )

        await recorder.start_new()
        await recorder.save()

        assert await repo.list_sessions() == []

    asyncio.run(run())


def test_retry_after_a_failed_append_does_not_duplicate_messages() -> None:
    """Messages appended before a failure are not appended again on retry."""

    async def run() -> None:
        first, second, third = (Message.user(t) for t in ("1", "2", "3"))
        repo = _FlakyStore(fail_on=second)
        session = await repo.create_session(model="m")
        engine = _engine((first, second, third))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=session.id, saved=0
        )

        with pytest.raises(StorageError):
            await recorder.save()
        assert await repo.get_messages(session.id) == [first]

        await recorder.save()

        assert await repo.get_messages(session.id) == [first, second, third]

    asyncio.run(run())
