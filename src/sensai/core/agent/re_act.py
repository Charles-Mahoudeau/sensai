"""ReAct agent alternating thoughts, tool actions and observations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.core.agent import Agent
from sensai.core.agent.events import AgentEvent, TurnCompleted
from sensai.core.models import TextDelta, ToolCall
from sensai.core.models.llm import Message, ThinkingDelta, ToolCallRequest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sensai.core.agent.base import AgentRun
    from sensai.core.ports import LLM

THOUGHT_SYSTEM_PROMPT = """\
Think step by step about the user's request. This is private, not the answer.
Write 1 to 3 short sentences:
- What do I already know?
- What is missing, and which tool could find it?
If nothing is missing, write: "I am ready to answer."
"""

ACTION_SYSTEM_PROMPT = """\
Follow your last thought.
If a tool is needed, call it now.
If no tool is needed, do not call any tool.
"""

OBSERVATION_SYSTEM_PROMPT = """\
Read the tool results above. This is private, not the answer.
Write 1 or 2 short sentences: what did I learn?
If I can answer now, write: "I am ready to answer."
Otherwise, write what is still missing.
"""

RESPONSE_SYSTEM_PROMPT = """\
Answer the user's request now.
Use what you learned above. Be clear and short.
Do not mention your thoughts or tools.
"""


class ReActAgent(Agent):
    """Agent that reasons privately through think/act/observe cycles."""

    def __init__(self, llm: LLM) -> None:
        """Initialize the agent with its chat model port."""
        super().__init__(llm)
        self._thinking_effort = 3

    async def _loop(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        async for event in self._thinking(run):
            yield event
        async for event in self._answer(run):
            yield event
        yield TurnCompleted(run.produced_messages)

    async def _thinking(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        for _ in range(self._thinking_effort):
            async for event in self._generate_thought(run):
                yield event
            async for event in self._generate_action(run):
                match event:
                    case TurnCompleted():
                        return
                yield event
            async for event in self._generate_observation(run):
                yield event

    async def _generate_thought(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        text_parts: list[str] = []

        async for event in self._llm.chat(
            [*run.messages, Message.system(THOUGHT_SYSTEM_PROMPT)]
        ):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    yield ThinkingDelta(text=text)

        # Save thinking message
        assistant = Message.assistant("".join(text_parts))
        run.add_message(assistant, final=False)

    async def _generate_action(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        text_parts: list[str] = []
        calls: list[ToolCall] = []

        async for event in self._llm.chat(
            [*run.messages, Message.system(ACTION_SYSTEM_PROMPT)],
            tools=self._tool_registry.spec(),
        ):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    yield ThinkingDelta(text=text)
                case ToolCallRequest(call=call):
                    calls.append(call)

        # Save thinking message
        assistant = Message.assistant("".join(text_parts), tool_calls=tuple(calls))
        run.add_message(assistant, final=False)

        if not calls:
            yield TurnCompleted(messages=[])
            return

        # Run tools
        async for event in self._run_tool_calls(run, calls):
            yield event

    async def _generate_observation(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        text_parts: list[str] = []

        async for event in self._llm.chat(
            [*run.messages, Message.system(OBSERVATION_SYSTEM_PROMPT)]
        ):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    yield ThinkingDelta(text=text)

        # Save thinking message
        assistant = Message.assistant("".join(text_parts))
        run.add_message(assistant, final=False)

    async def _answer(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        run.add_message(Message.system(RESPONSE_SYSTEM_PROMPT), final=False)
        text_parts: list[str] = []

        async for event in self._llm.chat(run.messages):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    yield TextDelta(text=text)
                case ThinkingDelta():
                    raise RuntimeError("thinking delta not expected")
                case ToolCallRequest():
                    raise RuntimeError("tool calls not expected")

        run.add_message(Message.assistant("".join(text_parts)), final=True)
