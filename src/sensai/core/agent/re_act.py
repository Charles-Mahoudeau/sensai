"""ReAct agent alternating thoughts, tool actions and observations."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Literal

from sensai.core.agent import Agent
from sensai.core.agent.events import (
    AgentEvent,
    ToolRunFinished,
    ToolRunStarted,
    TurnCompleted,
)
from sensai.core.agent.memory_extraction import MEMORY_WRITE_TOOLS
from sensai.core.agent.prompts import AgentPrompts
from sensai.core.agent.step import (
    Step,
    call_key,
    check_arguments,
    flat_step_schema,
    parse_step,
    step_schema,
)
from sensai.core.agent.structured import format_structured_output
from sensai.core.agent.thought_stream import ThoughtStream
from sensai.core.models import TextDelta, ThinkingEffort, ToolResult
from sensai.core.models.llm import ChatOptions, Message, ThinkingDelta
from sensai.core.ports import LLMResponseError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sensai.core.agent.base import AgentRun
    from sensai.core.agent.memory_extraction import MemoryExtractor
    from sensai.core.agent.memory_recall import MemoryRecall
    from sensai.core.agent.structured import (
        JsonSchemaOutput,
        OutputSchemaName,
        StructuredOutputCatalog,
    )
    from sensai.core.models import ToolCall, ToolSpec
    from sensai.core.ports import LLM
    from sensai.core.tools.registry import ToolRegistry

type AgentMode = Literal["answer", "plan"]

_MEMORY_READ_TOOL = "memory_read"
_REPEATED_CALL = "Repeated call skipped: its result is already in the conversation."
# A tool failing this many times in a turn is no longer offered in that turn.
_MAX_FAILURES = 2


def _describe_tools(tools: Sequence[ToolSpec]) -> str:
    """Render the tools, their descriptions and arguments for the thought prompt."""
    if not tools:
        return "(none)"
    return "\n".join(
        f"- {tool.name}: {tool.description}\n  arguments: {_describe_arguments(tool)}"
        for tool in tools
    )


def _describe_arguments(tool: ToolSpec) -> str:
    """Render arguments as `query (string, required), limit (integer)`."""
    properties = tool.parameters.get("properties") or {}
    required = set(tool.parameters.get("required") or ())
    if not properties:
        return "none"
    described = []
    for name, schema in properties.items():
        kind = schema.get("type") if isinstance(schema, dict) else None
        details = [kind if isinstance(kind, str) else "value"]
        if name in required:
            details.append("required")
        described.append(f"{name} ({', '.join(details)})")
    return ", ".join(described)


def _describe_notes(notes: Sequence[str]) -> str:
    """Number the thoughts of the turn, oldest first."""
    if len(notes) == 1:
        return notes[0]
    return "\n".join(f"{index}. {note}" for index, note in enumerate(notes, 1))


def _memory_query(messages: Sequence[Message]) -> str | None:
    """Return the latest non-empty user request for memory retrieval."""
    for message in reversed(messages):
        if message.role != "user":
            continue
        return message.content.strip() or None
    return None


class ReActAgent(Agent):
    """Agent that reasons privately and acts in steps, then answers.

    Each step is a thought in JSON ending with an action: call one tool, or
    answer. The schema of the reply only allows a tool that is offered, with
    arguments shaped like its parameters, so a tool call is never written as
    text. Once the agent can answer, or its budget is spent, a last call
    without tools writes the answer, which is the only text streamed to the
    user.
    """

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
        # Set once the model server refuses the step schema: from then on,
        # steps use the flat one.
        self._flat_steps = False

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
            # called at random.
            hidden |= MEMORY_WRITE_TOOLS
        if await self._recall_memory(run):
            # Every stored memory is in the system message: a search would
            # find nothing new, and an empty result reads as "nothing stored".
            hidden.add(_MEMORY_READ_TOOL)
        tools = [spec for spec in self._tool_registry.spec() if spec.name not in hidden]

        notes: list[str] = []
        seen: set[tuple[str, str]] = set()
        failures: Counter[str] = Counter()
        retry_cut = True
        for _ in range(self._thinking_effort.level):
            steps: list[Step] = []
            async for event in self._think(
                run, tools, notes, steps, retry_cut=retry_cut
            ):
                yield event
            step = steps[0]
            if step.thought:
                notes.append(step.thought)
            if step.call is None:
                if step.cut and retry_cut:
                    # Cut mid-sentence, the answer was forced, not concluded:
                    # once per turn, think again from the partial thought.
                    retry_cut = False
                    continue
                break
            spec = next(spec for spec in tools if spec.name == step.call.name)
            key = call_key(spec, step.call)
            if key in seen:
                # Asking again would loop: answer with what is already known.
                break
            seen.add(key)
            async for event in self._act(run, spec, step.call):
                if isinstance(event, ToolRunFinished) and event.result.is_error:
                    failures[spec.name] += 1
                yield event
            if failures[spec.name] >= _MAX_FAILURES:
                tools.remove(spec)

        async for event in self._answer(run, notes):
            yield event
        async for event in self._remember(run):
            yield event
        yield TurnCompleted(run.produced_messages)

    async def _think(
        self,
        run: AgentRun,
        tools: Sequence[ToolSpec],
        notes: Sequence[str],
        steps: list[Step],
        *,
        retry_cut: bool,
    ) -> AsyncIterator[AgentEvent]:
        """Stream a private thought, then append its step to `steps`.

        The model replies in JSON under the step schema: the `thought` text
        streams as `ThoughtStream` decodes it, and the action is read once the
        reply is complete. An empty delta first opens the thought in the
        front-end, which shows its clock while the model reads the prompt. The
        last delta tags an answer as ready, unless it is cut and `retry_cut`
        says the agent will think again.

        A server that refuses the schema before replying gets the flat one, for
        this step and every later one.
        """
        yield ThinkingDelta(text="")
        prompt = self._prompts.thought.format(tools=_describe_tools(tools))
        if notes:
            prompt += self._prompts.notes.format(thought=_describe_notes(notes))
        messages = [*run.messages, Message.user(prompt)]
        while True:
            schema = (flat_step_schema if self._flat_steps else step_schema)(tools)
            stream = ThoughtStream()
            parts: list[str] = []
            shown = False
            try:
                async for event in self._llm.chat(
                    messages, options=ChatOptions(response_schema=schema)
                ):
                    if isinstance(event, TextDelta):
                        parts.append(event.text)
                        if fragment := stream.feed(event.text):
                            shown = True
                            yield ThinkingDelta(text=fragment)
            except LLMResponseError:
                if parts or self._flat_steps:
                    raise
                self._logger.warning(
                    "The model server refused the step schema; using the flat one",
                    exc_info=True,
                )
                self._flat_steps = True
                continue
            break

        step = parse_step("".join(parts), tools)
        steps.append(step)
        # A reply that was not a step streamed nothing: show it whole.
        ready = step.call is None and not (step.cut and retry_cut)
        yield ThinkingDelta(text="" if shown else step.thought, ready=ready)

    async def _act(
        self, run: AgentRun, spec: ToolSpec, call: ToolCall
    ) -> AsyncIterator[AgentEvent]:
        """Run the call of a step, and record it as a tool call and its result.

        Arguments that don't match the tool's parameters are not run: the
        error is the result, so the next thought can fix them.
        """
        run.add_message(Message.assistant(tool_calls=(call,)), persist=False)
        if (problem := check_arguments(spec, call.arguments)) is None:
            async for event in self._run_tool_calls(run, (call,), persist=False):
                yield event
            return
        result = ToolResult.error(
            call.name, f"Invalid arguments, nothing was run: {problem}", call.id or ""
        )
        yield ToolRunStarted(call=call)
        yield ToolRunFinished(call=call, result=result)
        run.add_message(
            Message.tool(result.content, result.name, result.call_id), persist=False
        )

    async def _answer(
        self, run: AgentRun, notes: Sequence[str]
    ) -> AsyncIterator[AgentEvent]:
        """Write the answer, without tools, from the conversation and the notes.

        Free-form answers stream as they come; in plan mode the answer follows
        the plan schema and is shown once formatted.
        """
        block = (
            self._prompts.notes.format(thought=_describe_notes(notes)) if notes else ""
        )
        last = run.messages[-1]
        if last.role == "user":
            messages = [*run.messages[:-1], Message.user(last.content + block)]
        else:
            messages = [*run.messages, Message.user(self._prompts.answer + block)]

        output_name: OutputSchemaName | None = "plan" if self._mode == "plan" else None
        output = self._output_for(output_name) if output_name is not None else None
        options = ChatOptions(response_schema=output.schema) if output else None

        parts: list[str] = []
        async for event in self._llm.chat(messages, options=options):
            if isinstance(event, TextDelta):
                parts.append(event.text)
                if output is None:
                    yield event

        text = "".join(parts)
        if output is not None and output_name is not None:
            text = format_structured_output(output_name, output.parse(text))
            yield TextDelta(text)
        run.add_message(Message.assistant(text), persist=True)

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

    def _output_for(self, name: OutputSchemaName) -> JsonSchemaOutput | None:
        """Select the structured output contract for the current agent context."""
        return self._structured_output.select(name) if self._structured_output else None
