"""Turns what the user says about themself into memory tool calls.

Small models rarely choose the right memory tool on their own, so after each
answer one dedicated model call extracts the facts and the subjects to forget,
and the code decides between creating, updating and deleting a record.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from sensai.core.agent.structured import JsonSchemaOutput, StructuredOutputError
from sensai.core.models import TextDelta, ToolCall
from sensai.core.models.llm import ChatOptions, Message
from sensai.core.models.memory import MEMORY_CATEGORIES
from sensai.core.ports import LLMError, StorageError
from sensai.core.tools.builtin.memory.utils import find_similar

if TYPE_CHECKING:
    from sensai.core.models.memory import MemoryRecord
    from sensai.core.ports import LLM, MemoryRepository

_CREATE_TOOL = "memory_create"
_UPDATE_TOOL = "memory_update"
_DELETE_TOOL = "memory_delete"
# The tools only the extractor calls: the agent does not offer them to the model.
MEMORY_WRITE_TOOLS = frozenset({_CREATE_TOOL, _UPDATE_TOOL, _DELETE_TOOL})
# Existing subjects shown to the model so it reuses them instead of rewording.
_KNOWN_SUBJECTS = 20
# One sentence: text up to its closing punctuation.
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")

_FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "category": {"type": "string", "enum": list(MEMORY_CATEGORIES)},
                    "fact": {"type": "string"},
                },
                "required": ["subject", "category", "fact"],
                "additionalProperties": False,
            },
        },
        "forget": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["facts", "forget"],
    "additionalProperties": False,
}

_PROMPT = """\
You maintain the long-term memory of an assistant. Read the user's message and \
list every durable fact it states about the user: who they are, where they live, \
their job, family and pets, what they like, prefer, support or use, their \
projects, habits and goals, including corrections of earlier facts. Ignore \
requests, small talk, temporary states (such as being tired today), and general \
knowledge that is not about the user. A question never states a fact, even when \
it is about the user: never answer it or guess.

For each fact give:
- subject: a short label for what the fact is about. When the fact is about one \
of the existing subjects below, reuse that subject exactly.
- category: one of preference, identity, project, habit, goal or other, always \
in English.
- fact: one full sentence stating it about the user, keeping names as the user \
wrote them.

In forget, list the existing subjects below that the user explicitly asks to \
forget or delete, copied exactly. A new value for a subject is a fact, not \
something to forget.

Examples:
"Je vis à Nantes." -> {"facts": [{"subject": "ville", "category": "identity", \
"fact": "Vit à Nantes."}], "forget": []}
"Je supporte l'OL." -> {"facts": [{"subject": "équipe de foot préférée", \
"category": "preference", "fact": "Supporte l'Olympique lyonnais."}], \
"forget": []}
"Oublie que je supporte l'OL." -> {"facts": [], "forget": \
["équipe de foot préférée"]}
"Oublie où j'habite." -> {"facts": [], "forget": ["ville"]}
"Dans quelle ville j'habite ?" -> {"facts": [], "forget": []}
"Quelle heure est-il ?" -> {"facts": [], "forget": []}

Write subject and fact in the user's language. Reply with \
{"facts": [], "forget": []} when there is nothing to remember or forget.

Existing memories:
"""

_logger = logging.getLogger("MemoryExtractor")
_output = JsonSchemaOutput(_FACT_SCHEMA)


class MemoryExtractor:
    """Plans the memory tool calls that record a user's message."""

    def __init__(self, llm: LLM, memory: MemoryRepository) -> None:
        """Store the model used for extraction and the memory it compares with.

        Args:
            llm: The chat model asked to extract the facts.
            memory: The stored records, to tell a new fact from a changed one.
        """
        self._llm = llm
        self._memory = memory

    async def calls_for(self, user_message: str) -> list[ToolCall]:
        """Return the create, update and delete calls that record `user_message`.

        A failure to extract is logged and gives no call: the answer the user
        is waiting for must not depend on it.
        """
        try:
            return await self._plan(user_message)
        except (LLMError, StructuredOutputError, StorageError) as error:
            _logger.warning("Could not extract memories: %s", error)
            return []

    async def _plan(self, user_message: str) -> list[ToolCall]:
        known = list(await self._memory.find())[:_KNOWN_SUBJECTS]
        questions = _only_questions(user_message)
        if questions and not known:
            return []  # a question states no fact, and nothing can be forgotten
        facts, forget = await self._extract(user_message, known)
        if questions:
            # Asked for the facts of a question about the user, a small model
            # answers it with made-up ones ("Est fan du PSG").
            facts = []
        calls: list[ToolCall] = []
        # The model sometimes repeats a fact: one call per subject and record.
        subjects: set[str] = set()
        records: set[int] = set()
        for fact in facts:
            subject = fact["subject"].strip().casefold()
            if subject in subjects:
                continue
            subjects.add(subject)
            existing = _named(known, fact["subject"]) or await find_similar(
                self._memory, fact["subject"]
            )
            call_id = f"memory-extraction-{len(calls)}"
            if existing is None:
                arguments = {
                    "name": fact["subject"],
                    "type": fact["category"],
                    "description": fact["fact"],
                }
                calls.append(ToolCall(_CREATE_TOOL, arguments, call_id))
                continue
            if existing.id in records:
                continue
            # A record the message restates or changes is kept, not forgotten.
            records.add(existing.id)
            if existing.description != fact["fact"]:
                arguments = {"memory_id": existing.id, "description": fact["fact"]}
                calls.append(ToolCall(_UPDATE_TOOL, arguments, call_id))
        for subject in forget:
            # Deleting can't be undone: only a record with exactly this name.
            existing = _named(known, subject) or _named(
                list(await self._memory.find(query=subject)), subject
            )
            if existing is None or existing.id in records:
                continue
            records.add(existing.id)
            call_id = f"memory-extraction-{len(calls)}"
            calls.append(ToolCall(_DELETE_TOOL, {"memory_id": existing.id}, call_id))
        return calls

    async def _extract(
        self, user_message: str, known: list[MemoryRecord]
    ) -> tuple[list[dict[str, str]], list[str]]:
        """Ask the model for the facts and the subjects to forget of one message.

        Blank facts and subjects are dropped.
        """
        listing = "\n".join(f"- {r.name}: {r.description}" for r in known) or "(none)"
        messages = [
            Message.system(_PROMPT + listing),
            Message.user(user_message),
        ]
        options = ChatOptions(response_schema=_output.schema)
        text = "".join(
            [
                event.text
                async for event in self._llm.chat(messages, options=options)
                if isinstance(event, TextDelta)
            ]
        )
        data = _output.parse(text)
        facts = [f for f in data["facts"] if all(f[field].strip() for field in f)]
        forget = [subject for subject in data["forget"] if subject.strip()]
        return facts, forget


def _only_questions(message: str) -> bool:
    """Tell whether every sentence of `message` is a question."""
    sentences = [s.strip() for s in _SENTENCE.findall(message) if s.strip()]
    return bool(sentences) and all(s.endswith("?") for s in sentences)


def _named(records: list[MemoryRecord], subject: str) -> MemoryRecord | None:
    """Return the record whose name is exactly `subject`, ignoring case."""
    wanted = subject.strip().casefold()
    return next((r for r in records if r.name.casefold() == wanted), None)
