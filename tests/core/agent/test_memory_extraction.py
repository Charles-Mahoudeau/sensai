"""Tests for the automatic recording of what the user says about themself."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from sensai.core.agent.events import ToolRunStarted, TurnCompleted
from sensai.core.agent.memory_extraction import MemoryExtractor
from sensai.core.agent.re_act import ReActAgent
from sensai.core.models import Message, TextDelta
from sensai.core.models.memory import MEMORY_CATEGORIES
from sensai.core.ports import LLMResponseError
from sensai.core.tools.builtin import memory
from sensai.core.tools.registry import ToolRegistry
from tests.fakes import FakeLLM
from tests.fakes.memory import InMemoryMemoryStore

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.agent.events import AgentEvent


def _facts(*facts: tuple[str, str, str], forget: Sequence[str] = ()) -> list[TextDelta]:
    """Script a model reply holding the extracted facts and subjects to forget."""
    payload = {
        "facts": [
            {"subject": subject, "category": category, "fact": fact}
            for subject, category, fact in facts
        ],
        "forget": list(forget),
    }
    return [TextDelta(json.dumps(payload))]


def _calls(llm: FakeLLM, store: InMemoryMemoryStore, text: str) -> list:
    extractor = MemoryExtractor(llm, store)
    return asyncio.run(extractor.calls_for(text))


def test_a_new_fact_becomes_a_create_call() -> None:
    """A fact with no stored record on its subject is created."""
    llm = FakeLLM([_facts(("favorite car brand", "preference", "Prefers BMW cars"))])

    (call,) = _calls(llm, InMemoryMemoryStore(), "Je préfère les BMW.")

    assert call.name == "memory_create"
    assert call.arguments == {
        "name": "favorite car brand",
        "type": "preference",
        "description": "Prefers BMW cars",
    }
    assert llm.options[0] is not None
    schema = llm.options[0].response_schema
    assert schema is not None
    category = schema["properties"]["facts"]["items"]["properties"]["category"]
    assert category["enum"] == list(MEMORY_CATEGORIES)


def test_a_changed_fact_becomes_an_update_call() -> None:
    """The same subject, reworded or not, updates the stored record."""
    store = InMemoryMemoryStore()
    record = asyncio.run(
        store.create(
            name="preferred language", type="preference", description="Prefers Python"
        )
    )
    llm = FakeLLM([_facts(("Preferred Language", "preference", "Prefers Rust"))])

    (call,) = _calls(llm, store, "Finalement je préfère Rust.")

    assert call.name == "memory_update"
    assert call.arguments == {"memory_id": record.id, "description": "Prefers Rust"}
    system = llm.messages[0][0].content
    assert "preferred language: Prefers Python" in system


def test_an_unchanged_fact_or_no_fact_gives_no_call() -> None:
    """Repeating a stored fact, or saying nothing durable, writes nothing."""
    store = InMemoryMemoryStore()
    asyncio.run(
        store.create(
            name="preferred language", type="preference", description="Prefers Rust"
        )
    )

    same = _calls(
        FakeLLM([_facts(("preferred language", "preference", "Prefers Rust"))]),
        store,
        "Je préfère Rust.",
    )
    nothing = _calls(FakeLLM([_facts()]), store, "Quelle heure est-il ?")

    assert same == []
    assert nothing == []


def test_blank_facts_are_dropped() -> None:
    """An empty field from the model never reaches the memory tools."""
    llm = FakeLLM([_facts(("language", "preference", "  "))])

    assert _calls(llm, InMemoryMemoryStore(), "Je préfère Rust.") == []


def test_a_failed_extraction_gives_no_call() -> None:
    """Bad JSON or an unreachable model must not break the turn."""
    store = InMemoryMemoryStore()

    bad_json = _calls(FakeLLM([[TextDelta("not json")]]), store, "Je préfère Rust.")
    down = _calls(FakeLLM([[LLMResponseError("boom")]]), store, "Je préfère Rust.")

    assert bad_json == []
    assert down == []


# The model of the latest `_run_agent`, for tests that inspect its requests.
_LAST_LLM: list[FakeLLM] = []


def _run_agent(
    turns: Sequence[Sequence[object]], store: InMemoryMemoryStore, *, enabled: bool
) -> list[AgentEvent]:
    llm = FakeLLM(turns)  # ty: ignore[invalid-argument-type]
    _LAST_LLM[:] = [llm]
    registry = ToolRegistry()
    memory.register_self(registry, store)
    registry.set_all_enabled(enabled=enabled)
    agent = ReActAgent(llm, registry, memory_extractor=MemoryExtractor(llm, store))

    async def collect() -> list[AgentEvent]:
        return [e async for e in agent.run((Message.user("Je préfère les BMW."),))]

    return asyncio.run(collect())


def test_the_agent_records_the_fact_after_answering() -> None:
    """The record is written once the answer is out, and the UI sees the call."""
    store = InMemoryMemoryStore()
    turns = [
        [TextDelta('{"thought": "All known.", "ready": true}')],
        [TextDelta("Noté !")],
        _facts(("favorite car brand", "preference", "Prefers BMW cars")),
    ]

    events = _run_agent(turns, store, enabled=True)

    (record,) = asyncio.run(store.find())
    assert record.description == "Prefers BMW cars"
    assert [e.call.name for e in events if isinstance(e, ToolRunStarted)] == [
        "memory_create"
    ]
    assert events[-1] == TurnCompleted([Message.assistant("Noté !")])


def test_the_agent_records_nothing_when_the_tools_are_disabled() -> None:
    """With the tools off (`--no-tools`), no extraction is even attempted."""
    store = InMemoryMemoryStore()
    turns = [
        [TextDelta('{"thought": "All known.", "ready": true}')],
        [TextDelta("Noté !")],
    ]

    events = _run_agent(turns, store, enabled=False)

    assert asyncio.run(store.find()) == []
    assert events[-1] == TurnCompleted([Message.assistant("Noté !")])


def test_a_repeated_fact_gives_one_call() -> None:
    """The model sometimes lists a fact twice: only one record is planned."""
    fact = ("voiture préférée", "preference", "Préfère les voitures BMW.")
    llm = FakeLLM([_facts(fact, ("Voiture préférée", "preference", "Préfère BMW"))])

    calls = _calls(llm, InMemoryMemoryStore(), "Je préfère les voitures BMW.")

    assert [call.name for call in calls] == ["memory_create"]


def test_a_request_to_forget_becomes_a_delete_call() -> None:
    """A stored subject the user asks to forget is deleted."""
    store = InMemoryMemoryStore()
    record = asyncio.run(
        store.create(name="ville", type="identity", description="Habite à Lyon.")
    )
    llm = FakeLLM([_facts(forget=["Ville"])])

    (call,) = _calls(llm, store, "Oublie où j'habite.")

    assert call.name == "memory_delete"
    assert call.arguments == {"memory_id": record.id}


def test_only_a_stored_subject_that_is_not_restated_is_deleted() -> None:
    """Deleting can't be undone: an unknown or restated subject is kept."""
    store = InMemoryMemoryStore()
    asyncio.run(store.create(name="ville", type="identity", description="Lyon"))
    llm = FakeLLM(
        [
            _facts(forget=["ville natale"]),
            _facts(("ville", "identity", "Habite à Nantes."), forget=["ville"]),
        ]
    )
    extractor = MemoryExtractor(llm, store)

    unknown = asyncio.run(extractor.calls_for("Oublie ma ville natale."))
    restated = asyncio.run(extractor.calls_for("Oublie Lyon, j'habite à Nantes."))

    assert unknown == []
    assert [call.name for call in restated] == ["memory_update"]


def test_the_model_is_not_offered_the_write_tools() -> None:
    """The extractor writes memory: offered, the model would call them at random."""
    store = InMemoryMemoryStore()
    turns = [[TextDelta("Thinking.")], [TextDelta("Noté !")], _facts()]

    _run_agent(turns, store, enabled=True)

    offered = {spec.name for spec in _LAST_LLM[0].tools[1]}
    assert offered.isdisjoint({"memory_create", "memory_update", "memory_delete"})


def test_a_planned_call_to_a_disabled_tool_is_dropped() -> None:
    """With `memory_delete` turned off, a request to forget deletes nothing."""
    store = InMemoryMemoryStore()
    asyncio.run(store.create(name="ville", type="identity", description="Lyon"))
    llm = FakeLLM(
        [
            [TextDelta('{"thought": "OK.", "ready": true}')],
            [TextDelta("C'est noté.")],
            _facts(forget=["ville"]),
        ]
    )
    registry = ToolRegistry()
    memory.register_self(registry, store)
    registry.set_enabled("memory_delete", enabled=False)
    agent = ReActAgent(llm, registry, memory_extractor=MemoryExtractor(llm, store))

    async def collect() -> list[AgentEvent]:
        return [e async for e in agent.run((Message.user("Oublie ma ville."),))]

    events = asyncio.run(collect())

    assert not any(isinstance(e, ToolRunStarted) for e in events)
    assert len(asyncio.run(store.find())) == 1


def test_a_question_records_no_fact() -> None:
    """Asked about a question, a small model makes facts up: they are dropped.

    With nothing stored, nothing can be forgotten either: the model isn't asked.
    """
    store = InMemoryMemoryStore()
    unasked = FakeLLM([])

    assert _calls(unasked, store, "De quel club de foot suis-je fan ?") == []
    assert unasked.messages == []

    record = asyncio.run(store.create(name="ville", type="identity", description="X"))
    made_up = ("équipe de foot préférée", "preference", "Est fan du PSG.")
    llm = FakeLLM([_facts(made_up, forget=["ville"])])

    (call,) = _calls(
        llm, store, "De quel club suis-je fan ? Tu peux oublier ma ville ?"
    )

    assert call.name == "memory_delete"
    assert call.arguments == {"memory_id": record.id}


def test_a_statement_followed_by_a_question_keeps_its_facts() -> None:
    """Only a message made of questions alone is ignored."""
    llm = FakeLLM([_facts(("langage préféré", "preference", "Préfère Rust."))])

    calls = _calls(llm, InMemoryMemoryStore(), "Je préfère Rust. Un exemple ?")

    assert [call.name for call in calls] == ["memory_create"]
