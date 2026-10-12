"""Tests for the session recorder."""

from __future__ import annotations

import asyncio

from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import Message
from sensai.core.pipeline.base import Pipeline
from sensai.core.sessions import SessionRecorder
from tests.core.test_engine import ScriptedRunner
from tests.fakes import InMemorySessionStore


def _engine(history: tuple[Message, ...]) -> Engine:
    return Engine(ScriptedRunner(()), Pipeline(), EventBus(), history=history)


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
