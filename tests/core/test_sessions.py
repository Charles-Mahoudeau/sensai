"""Tests for the session recorder."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from sensai.core.engine import Engine
from sensai.core.events import Done, EventBus
from sensai.core.models import Message
from sensai.core.models.llm import ChatDone, Usage, UsageTotals
from sensai.core.pipeline.base import Pipeline
from sensai.core.ports import SessionNotFoundError, StorageError
from sensai.core.sessions import SessionRecorder
from sensai.core.usage import UsageMeter
from tests.core.test_engine import ScriptedRunner
from tests.fakes import InMemorySessionStore

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


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


class _StubTitler:
    """Returns scripted titles and records the exchanges it was given."""

    def __init__(self, *titles: str | None) -> None:
        self._titles = iter(titles)
        self.exchanges: list[tuple[str, str]] = []

    async def title_for(self, user_message: str, reply: str) -> str | None:
        self.exchanges.append((user_message, reply))
        return next(self._titles)


def _watched(
    engine: Engine, recorder: SessionRecorder
) -> tuple[asyncio.Task[None], Callable[[], Awaitable[None]]]:
    """Start `watch`, and return a function that publishes Done and lets it run."""
    task = asyncio.ensure_future(recorder.watch())

    async def turn_done() -> None:
        await engine._bus.publish(Done("s"))
        for _ in range(5):
            await asyncio.sleep(0)

    return task, turn_done


def test_watch_saves_and_titles_after_the_first_exchange() -> None:
    """The first complete exchange creates the session and names it, once."""

    async def run() -> None:
        repo = InMemorySessionStore()
        titler = _StubTitler("Greeting", "Other")
        engine = _engine((Message.user("hi"), Message.assistant("hello")))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=None, saved=0, titler=titler
        )
        task, turn_done = _watched(engine, recorder)
        await asyncio.sleep(0)

        await turn_done()
        await turn_done()
        task.cancel()

        [session] = await repo.list_sessions()
        assert session.title == "Greeting"
        assert titler.exchanges == [("hi", "hello")]
        assert len(await repo.get_messages(session.id)) == 2

    asyncio.run(run())


def test_watch_does_not_title_before_a_reply() -> None:
    """A turn that failed, leaving only the user message, is saved untitled."""

    async def run() -> None:
        repo = InMemorySessionStore()
        titler = _StubTitler("Never")
        engine = _engine((Message.user("hi"),))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=None, saved=0, titler=titler
        )
        task, turn_done = _watched(engine, recorder)
        await asyncio.sleep(0)

        await turn_done()
        task.cancel()

        [session] = await repo.list_sessions()
        assert session.title is None
        assert titler.exchanges == []

    asyncio.run(run())


def test_watch_retries_the_title_after_a_failure() -> None:
    """No title this turn means another attempt on the next one."""

    async def run() -> None:
        repo = InMemorySessionStore()
        titler = _StubTitler(None, "Greeting")
        engine = _engine((Message.user("hi"), Message.assistant("hello")))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=None, saved=0, titler=titler
        )
        task, turn_done = _watched(engine, recorder)
        await asyncio.sleep(0)

        await turn_done()
        assert [s.title for s in await repo.list_sessions()] == [None]
        await turn_done()
        task.cancel()

        assert [s.title for s in await repo.list_sessions()] == ["Greeting"]

    asyncio.run(run())


def test_a_new_session_after_start_new_is_titled_again() -> None:
    """Each session gets its own title."""

    async def run() -> None:
        repo = InMemorySessionStore()
        titler = _StubTitler("One", "Two")
        engine = _engine((Message.user("a"), Message.assistant("b")))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=None, saved=0, titler=titler
        )
        task, turn_done = _watched(engine, recorder)
        await asyncio.sleep(0)
        await turn_done()

        await recorder.start_new()
        engine.clear()
        engine._history.extend((Message.user("c"), Message.assistant("d")))
        await turn_done()
        task.cancel()

        titles = sorted(s.title or "" for s in await repo.list_sessions())
        assert titles == ["One", "Two"]

    asyncio.run(run())


def test_resume_saves_the_current_session_then_continues_the_chosen_one() -> None:
    """Later messages are appended to the resumed session, not the old one."""

    async def run() -> None:
        repo = InMemorySessionStore()
        old = await repo.create_session(model="m", title="Old")
        await repo.append_message(old.id, Message.user("old question"))
        meter = UsageMeter()
        engine = _engine((Message.user("current"),))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=None, saved=0, meter=meter
        )

        messages = await recorder.resume(old.id)
        engine.restore(messages)
        engine._history.append(Message.user("follow-up"))
        await recorder.save()

        assert list(messages) == [Message.user("old question")]
        assert await repo.get_messages(old.id) == [
            Message.user("old question"),
            Message.user("follow-up"),
        ]
        others = [s for s in await repo.list_sessions() if s.id != old.id]
        assert [await repo.get_messages(s.id) for s in others] == [
            [Message.user("current")]
        ]

    asyncio.run(run())


def test_resume_counts_usage_from_the_resumed_session() -> None:
    """The meter starts from the totals saved for that session."""

    async def run() -> None:
        repo = InMemorySessionStore()
        old = await repo.create_session(model="m")
        await repo.add_usage(old.id, _ONE_CALL)
        meter = UsageMeter()
        recorder = SessionRecorder(
            repo, _engine(()), model="m", session_id=None, saved=0, meter=meter
        )

        await recorder.resume(old.id)

        assert meter.total == _ONE_CALL

    asyncio.run(run())


def test_resume_of_an_unknown_session_keeps_the_current_one() -> None:
    """A failed switch changes nothing."""

    async def run() -> None:
        repo = InMemorySessionStore()
        current = await repo.create_session(model="m")
        engine = _engine((Message.user("hi"),))
        recorder = SessionRecorder(
            repo, engine, model="m", session_id=current.id, saved=0
        )

        with pytest.raises(SessionNotFoundError):
            await recorder.resume(999)
        await recorder.save()

        assert await repo.get_messages(current.id) == [Message.user("hi")]

    asyncio.run(run())
