"""Tests for the session recorder."""

from __future__ import annotations

import asyncio

import pytest

from sensai.core.engine import Engine
from sensai.core.events import EventBus
from sensai.core.models import Message
from sensai.core.models.llm import ChatDone, Usage, UsageTotals
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import StorageError
from sensai.core.sessions import SessionRecorder
from sensai.core.usage import UsageMeter
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


def test_clearing_then_quitting_stores_no_empty_session() -> None:
    """A cleared conversation that stays empty does not create a session."""

    async def run() -> None:
        repo = InMemorySessionStore()
        session = await repo.create_session(model="m")
        engine = _engine((Message.user("first"),))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=session.id, saved=0
        )

        await recorder.start_new()
        engine.clear()
        await recorder.save()

        assert [s.id for s in await repo.list_sessions()] == [session.id]
        assert await repo.get_messages(session.id) == [Message.user("first")]

    asyncio.run(run())


def test_start_new_keeps_an_empty_current_session() -> None:
    """Clearing an empty conversation does not create another empty session."""

    async def run() -> None:
        repo = InMemorySessionStore()
        session = await repo.create_session(model="m")
        recorder = SessionRecorder(
            repo, _engine(()), model="m", session_id=session.id, saved=0
        )

        await recorder.start_new()
        await recorder.start_new()

        assert [s.id for s in await repo.list_sessions()] == [session.id]

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


def _meter_with_one_call() -> UsageMeter:
    meter = UsageMeter()
    meter.record(ChatDone(Usage(completion_tokens=5, prompt_tokens=20)))
    return meter


_ONE_CALL = UsageTotals(prompt_tokens=20, completion_tokens=5, calls=1)


def test_save_adds_the_unsaved_usage_once() -> None:
    """Usage is added to the session, and not added again on the next save."""

    async def run() -> None:
        repo = InMemorySessionStore()
        session = await repo.create_session(model="m")
        recorder = SessionRecorder(
            repo,
            _engine((Message.user("hi"),)),
            model="m",
            session_id=session.id,
            saved=0,
            meter=_meter_with_one_call(),
        )

        await recorder.save()
        await recorder.save()

        assert (await repo.get_session(session.id)).usage == _ONE_CALL

    asyncio.run(run())


def test_usage_waits_for_a_session() -> None:
    """Without a session yet, usage is kept until the first message creates one."""

    async def run() -> None:
        repo = InMemorySessionStore()
        meter = _meter_with_one_call()
        engine = _engine(())
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=None, saved=0, meter=meter
        )

        await recorder.save()
        assert await repo.list_sessions() == []

        engine._history.append(Message.user("hi"))
        await recorder.save()

        [session] = await repo.list_sessions()
        assert session.usage == _ONE_CALL

    asyncio.run(run())


def test_start_new_counts_the_next_session_from_zero() -> None:
    """The old session keeps its usage; the meter restarts for the new one."""

    async def run() -> None:
        repo = InMemorySessionStore()
        session = await repo.create_session(model="m")
        meter = _meter_with_one_call()
        recorder = SessionRecorder(
            repo,
            _engine((Message.user("hi"),)),
            model="m",
            session_id=session.id,
            saved=0,
            meter=meter,
        )

        await recorder.start_new()

        assert (await repo.get_session(session.id)).usage == _ONE_CALL
        assert meter.total == UsageTotals()

    asyncio.run(run())


class _FailingUsageStore(InMemorySessionStore):
    """Fails to save usage, once."""

    def __init__(self) -> None:
        super().__init__()
        self._fail = True

    async def add_usage(self, session_id: int, usage: UsageTotals) -> None:
        if self._fail:
            self._fail = False
            raise StorageError("disk full")
        await super().add_usage(session_id, usage)


def test_usage_that_failed_to_save_is_saved_on_retry() -> None:
    """A failed write does not lose the usage."""

    async def run() -> None:
        repo = _FailingUsageStore()
        session = await repo.create_session(model="m")
        recorder = SessionRecorder(
            repo,
            _engine(()),
            model="m",
            session_id=session.id,
            saved=0,
            meter=_meter_with_one_call(),
        )

        with pytest.raises(StorageError):
            await recorder.save()
        await recorder.save()

        assert (await repo.get_session(session.id)).usage == _ONE_CALL

    asyncio.run(run())
