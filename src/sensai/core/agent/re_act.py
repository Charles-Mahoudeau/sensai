"""ReAct agent alternating thoughts, tool actions and observations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.core.agent import Agent
from sensai.core.agent.events import AgentEvent, TurnCompleted
from sensai.core.models import TextDelta, ToolCall
from sensai.core.models.llm import Message, ThinkingDelta, ToolCallRequest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.agent.base import AgentRun
    from sensai.core.models import ToolSpec
    from sensai.core.ports import LLM
    from sensai.core.tools.registry import ToolRegistry

THOUGHT_PROMPT = """\
Before answering, think privately about the request above. This is not the answer.
Tools you can call:
{tools}

Write 1 to 3 short sentences:
- What do I actually know for sure, from the conversation or tool results?
- What is missing or could be outdated? Which tool would provide it?
Prefer checking with a tool over relying on memory: facts, dates, news, files,
numbers and anything specific to the user's context must come from a tool.
Only if the conversation already contains everything needed (or the request is
simple small talk), write: "I am ready to answer."
"""

NOTES_TEMPLATE = """\

[Private notes, the user cannot see them: {thought}
Now call a tool if your notes say you need one, otherwise answer the user.]"""

ANSWER_PROMPT = """\
Answer the user's request now, using what you learned. Match the format and \
level of detail the user asked for: a full report or detailed request \
deserves a long, structured answer, a simple question a short one.\
"""

# Llama-style chat templates only render the tool definitions in the last
# message when it is a user one, and only open the assistant turn after a user or
# tool message. Every call below therefore ends with a user or tool message.


def _with_notes(messages: Sequence[Message], thought: str) -> list[Message]:
    """Attach the private thought to the end of the conversation.

    The notes are folded into the last message when it is the user's, so it keeps
    carrying the request; after a tool result they become a user message of
    their own. The history itself is left untouched.
    """
    notes = NOTES_TEMPLATE.format(thought=thought)
    last = messages[-1]
    if last.role == "user":
        return [*messages[:-1], Message.user(last.content + notes)]
    return [*messages, Message.user(notes.lstrip())]


def _describe_tools(tools: Sequence[ToolSpec]) -> str:
    """Render the tool names and descriptions for the thought prompt."""
    if not tools:
        return "(none)"
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)


def _is_ready(thought: str) -> bool:
    """Tell whether the thought concluded that no more information is needed."""
    lowered = thought.lower()
    return "ready to answer" in lowered and "not ready" not in lowered


class ReActAgent(Agent):
    """Agent that reasons privately, then acts or answers, in think/act cycles."""

    def __init__(self, llm: LLM, tool_registry: ToolRegistry) -> None:
        """Initialize the agent with its chat model port and shared tools."""
        super().__init__(llm, tool_registry)
        self._thinking_effort = 10

    async def _loop(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        for _ in range(self._thinking_effort):
            thoughts: list[str] = []
            async for event in self._generate_thought(run, thoughts):
                yield event
            calls: list[ToolCall] = []
            thought = thoughts[0]
            # Llama templates push the model to answer with a function call
            # whenever tools are offered, so offer none once it is ready.
            async for event in self._act(
                run, thought, calls, use_tools=not _is_ready(thought)
            ):
                yield event
            if not calls:
                yield TurnCompleted(run.produced_messages)
                return
            async for event in self._run_tool_calls(run, calls, persist=False):
                yield event

        # Thinking budget spent: answer with what was gathered, without tools.
        async for event in self._act(
            run, "I have gathered enough.", [], use_tools=False
        ):
            yield event
        yield TurnCompleted(run.produced_messages)

    async def _generate_thought(
        self, run: AgentRun, thoughts: list[str]
    ) -> AsyncIterator[AgentEvent]:
        """Stream a private thought, then append it to `thoughts`."""
        text_parts: list[str] = []

        prompt = THOUGHT_PROMPT.format(
            tools=_describe_tools(self._tool_registry.spec())
        )
        async for event in self._llm.chat([*run.messages, Message.user(prompt)]):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    yield ThinkingDelta(text=text)

        thought = "".join(text_parts).strip()
        thoughts.append(thought)
        if _is_ready(thought):
            yield ThinkingDelta(text="", ready=True)

    async def _act(
        self,
        run: AgentRun,
        thought: str,
        calls: list[ToolCall],
        *,
        use_tools: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        """Call the model once; text is the answer, tool calls fill `calls`.

        A text-only reply ends the turn and is persisted as the final answer.
        When tool calls are requested, any accompanying text is not persisted.
        """
        text_parts: list[str] = []
        tools = self._tool_registry.spec() if use_tools else ()

        if use_tools:
            messages = _with_notes(run.messages, thought)
        elif run.messages[-1].role == "user":
            messages = list(run.messages)
        else:
            messages = [*run.messages, Message.user(ANSWER_PROMPT)]

        async for event in self._llm.chat(messages, tools=tools):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    yield event
                case ToolCallRequest(call=call):
                    calls.append(call)

        text = "".join(text_parts)
        if calls:
            run.add_message(
                Message.assistant(text, tool_calls=tuple(calls)), persist=False
            )
        else:
            run.add_message(Message.assistant(text), persist=True)
