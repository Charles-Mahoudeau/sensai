"""ReAct agent alternating thoughts, tool actions and observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sensai.core.agent import Agent
from sensai.core.agent.events import AgentEvent, TurnCompleted
from sensai.core.agent.memory_extraction import MEMORY_WRITE_TOOLS
from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.structured import (
    JsonSchemaOutput,
    StructuredOutputError,
    format_structured_output,
)
from sensai.core.models import TextDelta, ThinkingEffort, ToolCall
from sensai.core.models.llm import ChatOptions, Message, ThinkingDelta, ToolCallRequest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.agent.base import AgentRun
    from sensai.core.agent.memory_extraction import MemoryExtractor
    from sensai.core.agent.memory_recall import MemoryRecall
    from sensai.core.agent.structured import (
        OutputSchemaName,
        StructuredOutputCatalog,
    )
    from sensai.core.models import ToolSpec
    from sensai.core.ports import LLM
    from sensai.core.tools.registry import ToolRegistry

type AgentMode = Literal["answer", "plan"]
# Llama-style chat templates only render the tool definitions in the last
# message when it is a user one, and only open the assistant turn after a user or
# tool message. Every call below therefore ends with a user or tool message.

_MEMORY_READ_TOOL = "memory_read"
# A reply starting like this may be a tool call written as text, not an answer.
_BARE_CALL_START = "{\"'`"
_REPEATED_CALL = "Repeated call skipped: its result is already in the conversation."
# The thought comes first, so the model reasons before it decides.
_THOUGHT_OUTPUT = JsonSchemaOutput(
    {
        "type": "object",
        "properties": {
            "thought": {"type": "string"},
            "ready": {"type": "boolean"},
        },
        "required": ["thought", "ready"],
        "additionalProperties": False,
    }
)


@dataclass(frozen=True, slots=True)
class _Thought:
    """A private thought, and whether it concluded the answer can be written."""

    text: str
    ready: bool


def _with_notes(
    messages: Sequence[Message], thought: str, template: str
) -> list[Message]:
    """Attach the private thought to the end of the conversation.

    The notes are folded into the last message when it is the user's, so it keeps
    carrying the request; after a tool result they become a user message of
    their own. The history itself is left untouched.
    """
    notes = template.format(thought=thought)
    last = messages[-1]
    if last.role == "user":
        return [*messages[:-1], Message.user(last.content + notes)]
    return [*messages, Message.user(notes.lstrip())]


def _describe_tools(tools: Sequence[ToolSpec]) -> str:
    """Render the tool names and descriptions for the thought prompt."""
    if not tools:
        return "(none)"
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)


def _parse_thought(text: str) -> _Thought:
    """Read a structured thought; one that is not valid JSON is not ready."""
    try:
        data = _THOUGHT_OUTPUT.parse(text)
    except StructuredOutputError:
        return _Thought(text.strip(), ready=False)
    return _Thought(data["thought"].strip(), ready=data["ready"])


def _starts_with_json(text: str) -> bool:
    """Tell whether a reply opens with a JSON value, such as `{}`, whatever follows."""
    body = text.strip().removeprefix("```json").removeprefix("```").lstrip()
    try:
        json.JSONDecoder().raw_decode(body)
    except ValueError:
        return False
    return True


def _call_key(call: ToolCall) -> tuple[str, str]:
    """Identify a tool call by its name and arguments."""
    return call.name, json.dumps(dict(call.arguments), sort_keys=True, default=str)


def _memory_query(messages: Sequence[Message]) -> str | None:
    """Return the latest non-empty user request for memory retrieval."""
    for message in reversed(messages):
        if message.role != "user":
            continue
        return message.content.strip() or None
    return None


class ReActAgent(Agent):
    """Agent that reasons privately, then acts or answers, in think/act cycles."""

    def __init__(
        self,
        llm: LLM,
        tool_registry: ToolRegistry,
        prompts: AgentPrompts | None = None,
        *,
        mode: AgentMode = "answer",
        structured_output: StructuredOutputCatalog | None = None,
        memory_extractor: MemoryExtractor | None = None,
        memory_recall: MemoryRecall | None = None,
    ) -> None:
        """Initialize the agent with its chat model port, tools and prompt texts.

        Args:
            llm: The chat model.
            tool_registry: The tools offered to the LLM and run on its request.
            prompts: The ReAct prompts; the code defaults when `None`.
            mode: Selects free-form answers or structured plans.
            structured_output: Available schemas for structured agent modes.
            memory_extractor: Records what the user says about themself after
                each answer; no automatic recording when `None`.
            memory_recall: Shows the stored memories in the system message
                before each turn; none are shown when `None`.
        """
        super().__init__(llm, tool_registry)
        self._prompts = prompts or AgentPrompts.defaults()
        self._thinking_effort = ThinkingEffort.MEDIUM
        self._mode = mode
        self._structured_output = structured_output
        self._memory_extractor = memory_extractor
        self._memory_recall = memory_recall

    @property
    def thinking_effort(self) -> ThinkingEffort:
        """How much the agent reasons before answering."""
        return self._thinking_effort

    @thinking_effort.setter
    def thinking_effort(self, value: ThinkingEffort) -> None:
        self._thinking_effort = value

    async def _loop(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        hidden: set[str] = set()
        if self._memory_extractor is not None:
            # The extractor writes memory. Offered to the model, these tools get
            # called at random whenever the template pushes it to call one.
            hidden |= MEMORY_WRITE_TOOLS
        if await self._recall_memory(run):
            # Every stored memory is in the system message: a search would
            # find nothing new, and an empty result reads as "nothing stored".
            hidden.add(_MEMORY_READ_TOOL)
        tools = tuple(
            spec for spec in self._tool_registry.spec() if spec.name not in hidden
        )

        seen: set[tuple[str, str]] = set()
        for _ in range(self._thinking_effort.level):
            thoughts: list[_Thought] = []
            async for event in self._generate_thought(run, tools, thoughts):
                yield event
            calls: list[ToolCall] = []
            thought = thoughts[0]
            # Llama templates push the model to answer with a function call
            # whenever tools are offered, so offer none once it is ready.
            async for event in self._act(
                run, thought.text, calls, tools=None if thought.ready else tools
            ):
                yield event
            if not calls:
                async for event in self._finish(run):
                    yield event
                return
            keys = {_call_key(call) for call in calls}
            if keys & seen:
                # Asking again would loop: answer with what is already known.
                for call in calls:
                    run.add_message(
                        Message.tool(_REPEATED_CALL, call.name, call.id or ""),
                        persist=False,
                    )
                break
            seen |= keys
            # A3 will intercept confirmation-required calls here and select
            # the `permission_decision` schema before executing any tool.
            async for event in self._run_tool_calls(run, calls, persist=False):
                yield event

        # Thinking budget spent: answer with what was gathered, without tools.
        async for event in self._act(run, "I have gathered enough.", [], tools=None):
            yield event
        async for event in self._finish(run):
            yield event

    async def _finish(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        """Record what the user said about themself, then end the turn."""
        async for event in self._remember(run):
            yield event
        yield TurnCompleted(run.produced_messages)

    async def _remember(self, run: AgentRun) -> AsyncIterator[AgentEvent]:
        """Run the memory writes the extractor plans for the user's message.

        A planned call whose tool is disabled is dropped; with every write tool
        disabled, nothing is even extracted.
        """
        if self._memory_extractor is None:
            return
        enabled = {spec.name for spec in self._tool_registry.spec()}
        if not enabled & MEMORY_WRITE_TOOLS:
            return
        if (message := _memory_query(run.messages)) is None:
            return

        calls = await self._memory_extractor.calls_for(message)
        calls = [call for call in calls if call.name in enabled]
        async for event in self._run_tool_calls(run, calls, persist=False):
            yield event

    async def _recall_memory(self, run: AgentRun) -> bool:
        """Show the stored memories in this run's system message.

        It only runs while `memory_read` is enabled, so `--no-tools` turns it
        off.

        Returns:
            Whether every stored memory is shown, so `memory_read` has nothing
            more to find.
        """
        if self._memory_recall is None:
            return False
        if _MEMORY_READ_TOOL not in {spec.name for spec in self._tool_registry.spec()}:
            return False

        recollection = await self._memory_recall.recall(
            _memory_query(run.messages) or ""
        )
        if recollection.text:
            run.extend_system_message(recollection.text)
        return recollection.complete

    async def _generate_thought(
        self, run: AgentRun, tools: Sequence[ToolSpec], thoughts: list[_Thought]
    ) -> AsyncIterator[AgentEvent]:
        """Ask for a private thought and whether it is ready; append it to `thoughts`.

        The model replies in JSON, so the thought is shown once complete; an
        empty delta first opens it in the front-end, which then shows its clock.
        """
        yield ThinkingDelta(text="")
        prompt = self._prompts.thought.format(tools=_describe_tools(tools))
        options = ChatOptions(response_schema=_THOUGHT_OUTPUT.schema)
        text = "".join(
            [
                event.text
                async for event in self._llm.chat(
                    [*run.messages, Message.user(prompt)], options=options
                )
                if isinstance(event, TextDelta)
            ]
        )

        thought = _parse_thought(text)
        thoughts.append(thought)
        yield ThinkingDelta(text=thought.text, ready=thought.ready)

    async def _act(
        self,
        run: AgentRun,
        thought: str,
        calls: list[ToolCall],
        *,
        tools: Sequence[ToolSpec] | None,
        retry_bare_call: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        """Call the model once; text is the answer, tool calls fill `calls`.

        With `tools`, even none, the thought joins the request as notes and the
        tools are offered; `None` asks for the final answer instead.
        A text-only reply ends the turn and is persisted as the final answer.
        When tool calls are requested, any accompanying text is not persisted.
        A reply that is only a tool call written as text, or with tools one that
        opens with JSON, such as `{}`, is dropped and asked again without tools.
        """
        text_parts: list[str] = []
        held: list[str] | None = None
        use_tools = tools is not None

        if use_tools:
            messages = _with_notes(run.messages, thought, self._prompts.notes)
        elif run.messages[-1].role == "user":
            messages = list(run.messages)
        else:
            messages = [*run.messages, Message.user(self._prompts.answer)]

        # Free-form answers stream directly; only plan mode needs a JSON contract.
        output_name: OutputSchemaName | None = "plan" if self._mode == "plan" else None
        output = self._output_for(output_name) if output_name is not None else None
        is_structured_response = output is not None and not use_tools
        options = (
            ChatOptions(response_schema=output.schema)
            if is_structured_response
            else None
        )

        async for event in self._llm.chat(messages, tools=tools or (), options=options):
            match event:
                case TextDelta(text=text):
                    text_parts.append(text)
                    if is_structured_response:
                        pass
                    elif held is not None:
                        held.append(text)
                    elif (start := "".join(text_parts).lstrip()[:1]) and (
                        start in _BARE_CALL_START
                    ):
                        held = [text]
                    else:
                        yield event
                case ToolCallRequest(call=call):
                    calls.append(call)

        text = "".join(text_parts)
        if held is not None:
            # Pushed to call a tool, a small model may write `{}` instead.
            failed_call = self._is_bare_tool_call(text) or (
                use_tools and _starts_with_json(text)
            )
            if retry_bare_call and not calls and failed_call:
                self._logger.info("Dropped a tool call written as text: %r", text)
                async for event in self._act(
                    run, thought, calls, tools=None, retry_bare_call=False
                ):
                    yield event
                return
            yield TextDelta("".join(held))
        if calls:
            run.add_message(
                Message.assistant(text, tool_calls=tuple(calls)), persist=False
            )
        else:
            if output is not None and output_name is not None and not use_tools:
                parsed = output.parse(text)
                text = format_structured_output(output_name, parsed)
                yield TextDelta(text)
            run.add_message(Message.assistant(text), persist=True)

    def _is_bare_tool_call(self, text: str) -> bool:
        """Tell whether a reply is only a tool name or call written as text."""
        names = {info.spec.name for info in self._tool_registry.tools()}
        stripped = text.strip()
        if stripped.strip("`\"' ") in names:
            return True
        body = stripped.removeprefix("```json").removeprefix("```")
        try:
            data = json.loads(body.removesuffix("```").strip())
        except ValueError:
            return False
        return (
            isinstance(data, dict)
            and isinstance(data.get("name"), str)
            and data["name"] in names
        )

    def _output_for(self, name: OutputSchemaName) -> JsonSchemaOutput | None:
        """Select the structured output contract for the current agent context."""
        return self._structured_output.select(name) if self._structured_output else None
