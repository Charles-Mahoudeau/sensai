"""Public facade front-ends use to submit messages and subscribe to events."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sensai.core import agent
from sensai.core.agent.events import TurnCompleted
from sensai.core.errors import EngineError, SensaiError, SubmissionInProgressError
from sensai.core.events import (
    Done,
    ErrorEvent,
    Event,
    EventBus,
    MessageCompleted,
    MessageStarted,
    ThinkingGenerated,
    TokenGenerated,
)
from sensai.core.events.types import ToolRunFinished, ToolRunStarted
from sensai.core.models import Message, TextDelta, ThinkingEffort
from sensai.core.models.llm import ThinkingDelta
from sensai.core.persona import render_persona
from sensai.core.pipeline.base import Pipeline, ShortCircuit
from sensai.core.ports import PersonaNotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Iterable, Sequence

    from sensai.core.agent.events import AgentEvent
    from sensai.core.model_memory import ModelMemory
    from sensai.core.models import McpServerStatus, ToolInfo
    from sensai.core.models.llm import LoadedModel
    from sensai.core.models.persona import Persona
    from sensai.core.ports import PersonaSource
    from sensai.core.tools.registry import ToolRegistry


class Runner(Protocol):
    """Protocol for a message processing runner."""

    def run(self, messages: tuple[Message, ...]) -> AsyncIterator[AgentEvent]:
        """Run the message processing pipeline for the given message."""
        ...


@runtime_checkable
class ThinkingRunner(Protocol):
    """A runner whose reasoning effort can be changed between turns."""

    thinking_effort: ThinkingEffort


class Engine:
    """Coordinate the pipeline, runner and public event bus."""

    def __init__(
        self,
        runner: Runner,
        pipeline: Pipeline,
        bus: EventBus,
        *,
        system_prompt: str = "",
        profile: str = "",
        personas: PersonaSource | None = None,
        history: Sequence[Message] = (),
        tools: ToolRegistry | None = None,
        mcp_servers: Sequence[McpServerStatus] = (),
        model_memory: ModelMemory | None = None,
    ) -> None:
        """Initialize the engine with its processing dependencies.

        Args:
            runner: Runs each turn.
            pipeline: Prepares the messages, or answers without the runner.
            bus: Carries the public events.
            system_prompt: The base of the system message sent on every turn.
            profile: The rendered user profile, after the persona.
            personas: Where the personas to switch to come from; none if None.
            history: Messages restored from a previous session.
            tools: The runner's tools, listed and toggled by front-ends.
            mcp_servers: The outcome of connecting to each MCP server.
            model_memory: Reads the model's memory footprint; none if None.
        """
        self._runner = runner
        self._pipeline = pipeline
        self._bus = bus
        self._system_prompt = system_prompt
        self._profile = profile
        self._personas = personas
        self._persona: Persona | None = None
        self._history: list[Message] = list(history)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._tools = tools
        self._mcp_servers = tuple(mcp_servers)
        self._model_memory = model_memory

    @property
    def thinking_effort(self) -> ThinkingEffort:
        """How much the runner reasons, or NONE if it does not support reasoning.

        The runner owns the value; changes apply from the next submission.
        """
        if isinstance(self._runner, ThinkingRunner):
            return self._runner.thinking_effort
        return ThinkingEffort.NONE

    @thinking_effort.setter
    def thinking_effort(self, value: ThinkingEffort) -> None:
        if isinstance(self._runner, ThinkingRunner):
            self._runner.thinking_effort = value

    def cycle_thinking_effort(self) -> ThinkingEffort:
        """Switch the runner to the next thinking effort, wrapping after the highest."""
        self.thinking_effort = self.thinking_effort.next()
        return self.thinking_effort

    def tools(self) -> tuple[ToolInfo, ...]:
        """Every tool the runner may be offered, enabled or not."""
        return self._tools.tools() if self._tools is not None else ()

    def set_tool_enabled(self, name: str, *, enabled: bool) -> None:
        """Offer a tool to the runner or not, from the next submission.

        Raises:
            KeyError: No tool is called `name`.
        """
        if self._tools is None:
            raise KeyError(f"Unknown tool {name!r}")
        self._tools.set_enabled(name, enabled=enabled)

    def set_tools_enabled(
        self, *, enabled: bool, names: Iterable[str] | None = None
    ) -> None:
        """Enable or disable several tools (every one when `names` is None).

        Raises:
            KeyError: One of `names` is not a tool; nothing changed.
        """
        if self._tools is not None:
            self._tools.set_all_enabled(enabled=enabled, names=names)
        elif names is not None and (unknown := list(names)):
            raise KeyError(f"Unknown tools {unknown!r}")

    def mcp_servers(self) -> tuple[McpServerStatus, ...]:
        """The MCP servers configured at startup, connected or not."""
        return self._mcp_servers

    async def loaded_model(self) -> LoadedModel | None:
        """The memory the model uses, or None if unknown or not loaded right now.

        Raises:
            LLMError: The model server cannot be reached or misbehaves.
        """
        if self._model_memory is None:
            return None
        return await self._model_memory.current()

    def subscribe(self) -> AsyncGenerator[Event]:
        """Subscribe a front-end to the public event stream."""
        return self._bus.subscribe()

    # only for message write by an user like in a web
    # submit ->>> run ->>>> stream_reply
    def submit(self, text: str) -> str:
        """Submit a user message for processing."""
        if self._tasks:
            raise SubmissionInProgressError("A submission is already in progress.")
        submission_id = uuid.uuid4().hex
        self._history.append(Message.user(text))
        task = asyncio.create_task(self._run(submission_id))
        self._tasks[submission_id] = task
        return submission_id

    def clear(self) -> None:
        """Forget the conversation; the next submission starts from scratch.

        Raises:
            SubmissionInProgressError: A submission is still running.
        """
        if self._tasks:
            raise SubmissionInProgressError("A submission is already in progress.")
        self._history.clear()

    def interrupt(self, submission_id: str) -> None:
        """Interrupt a running submission."""
        task = self._tasks.get(submission_id)
        if task is not None:
            task.cancel()

    async def _run(self, submission_id: str) -> None:
        try:
            await self._bus.publish(MessageStarted(submission_id))  # start

            messages = tuple(self._history)
            system = self._system_message()
            if system:
                messages = (Message.system(system), *messages)
            result = self._pipeline.run(messages)  # pipeline

            if isinstance(result, ShortCircuit):  # already has a reply
                self._history.append(result.reply)
                await self._bus.publish(MessageCompleted(submission_id, result.reply))

            else:  # requires asking the model
                replies = await self._stream_reply(submission_id, result.messages)
                if not replies:
                    raise SensaiError("no replies received from the model")
                self._history.extend(replies)
                await self._bus.publish(MessageCompleted(submission_id, replies[-1]))
        except SensaiError as error:
            await self._bus.publish(ErrorEvent(submission_id, error))
        except Exception as error:
            await self._bus.publish(ErrorEvent(submission_id, EngineError(str(error))))
        finally:
            self._tasks.pop(submission_id, None)
            await self._bus.publish(Done(submission_id))  # end

    async def _stream_reply(
        self, submission_id: str, messages: tuple[Message, ...]
    ) -> list[Message]:
        async for event in self._runner.run(messages):
            match event:
                case TextDelta(text):
                    await self._bus.publish(TokenGenerated(submission_id, text))
                case ThinkingDelta(text, ready):
                    await self._bus.publish(
                        ThinkingGenerated(submission_id, text, ready)
                    )
                case agent.events.ToolRunStarted(call):
                    await self._bus.publish(ToolRunStarted(submission_id, call))
                case agent.events.ToolRunFinished(call, result):
                    await self._bus.publish(
                        ToolRunFinished(submission_id, call, result)
                    )
                case TurnCompleted(messages=produced):
                    return produced
        raise RuntimeError("TurnCompleted event not received")

    @property
    def history(self) -> tuple[Message, ...]:
        """The conversation so far, oldest first."""
        return tuple(self._history)

    @property
    def persona(self) -> Persona | None:
        """The persona the agent acts as, or None for the base system prompt."""
        return self._persona

    def persona_names(self) -> tuple[str, ...]:
        """Every persona available right now, sorted by name."""
        return tuple(self._personas.names()) if self._personas is not None else ()

    def set_persona(self, name: str) -> Persona | None:
        """Switch to the current version of a persona, keeping the history.

        The persona is read again from its source, so an edited persona is
        picked up by switching to it. Applies from the next submission.

        Raises:
            PersonaNotFoundError: No persona is called `name`.
            PersonaInvalidError: The persona exists but is not valid.
            SubmissionInProgressError: A submission is still running.
        """
        if self._tasks:
            raise SubmissionInProgressError("A submission is already in progress.")
        if self._personas is None:
            raise PersonaNotFoundError(f"Unknown persona {name!r}")
        self._persona = self._personas.load(name)
        return self._persona

    def _system_message(self) -> str:
        """Join the base prompt, the persona and the profile, skipping empty ones."""
        persona = render_persona(self._persona) if self._persona is not None else ""
        parts = (self._system_prompt, persona, self._profile)
        return "\n\n".join(part for part in parts if part)
