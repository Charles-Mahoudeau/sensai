"""Names a session after its first exchange."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sensai.core.models import TextDelta
from sensai.core.models.llm import ChatOptions, Message
from sensai.core.ports import LLMError
from sensai.core.prompts.defaults import SESSION_TITLE, load_defaults

if TYPE_CHECKING:
    from sensai.core.ports import LLM

_MAX_LENGTH = 60
# Room for a short title, and for a reasoning model that thinks despite `think`.
_MAX_TOKENS = 64
# Enough to tell the topic; a pasted document need not be sent whole.
_MAX_EXCHANGE = 1000
_QUOTES = "\"'`«»\u201c\u201d\u2018\u2019 "
_TRAILING_PUNCTUATION = ".!?…:;,"

_logger = logging.getLogger(__name__)


class SessionTitler:
    """Asks the model for a short title of a conversation."""

    def __init__(self, llm: LLM, prompt: str | None = None) -> None:
        """Store the model that writes the titles.

        Args:
            llm: The chat model asked for the title.
            prompt: The `session_title` prompt; the code default when `None`.
        """
        self._llm = llm
        self._prompt = prompt or load_defaults()[SESSION_TITLE]

    async def title_for(self, user_message: str, reply: str) -> str | None:
        """Return a title for an exchange, or None if the model gave none.

        A failure is logged and gives no title: the conversation must not
        depend on it.
        """
        messages = [
            Message.system(self._prompt),
            Message.user(
                f"User: {user_message[:_MAX_EXCHANGE]}\n\n"
                f"Assistant: {reply[:_MAX_EXCHANGE]}"
            ),
        ]
        options = ChatOptions(think=False, temperature=0.3, max_tokens=_MAX_TOKENS)
        try:
            text = "".join(
                [
                    event.text
                    async for event in self._llm.chat(messages, options=options)
                    if isinstance(event, TextDelta)
                ]
            )
        except LLMError as error:
            _logger.warning("Could not title the session: %s", error)
            return None
        return _clean(text)


def _clean(text: str) -> str | None:
    """Keep the first line of `text`, without quotes, final punctuation or excess."""
    lines = text.strip().splitlines()
    title = lines[0].strip(_QUOTES).rstrip(_TRAILING_PUNCTUATION) if lines else ""
    title = title.removeprefix("Title:").strip(_QUOTES)
    if len(title) > _MAX_LENGTH:
        title = title[: _MAX_LENGTH - 1].rstrip() + "…"
    return title or None
