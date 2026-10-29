"""Decodes the private thought of the ReAct agent while its JSON streams.

The thought is asked for in JSON, `{"thought": "...", "action": "answer"}`, so
the model's reasoning arrives inside a JSON string. Decoding it chunk by chunk keeps
the reasoning visible as it is written, instead of only once the reply is done.
"""

from __future__ import annotations

import re

# Where the `thought` string starts in the streamed JSON.
_THOUGHT_START = re.compile(r'\s*\{\s*"thought"\s*:\s*"')
_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class ThoughtStream:
    """Decodes the `thought` string of a JSON thought while it streams.

    The schema puts `thought` first, so its text can be shown as it comes. An
    escape split between two chunks, such as an accent as `u00e9`, waits for
    the next one.
    """

    def __init__(self) -> None:
        """Start before the opening quote of the thought."""
        self._raw = ""
        self._index: int | None = None
        self._done = False

    def feed(self, chunk: str) -> str:
        """Add a chunk of the reply; return the newly decoded part of the thought."""
        self._raw += chunk
        if self._done:
            return ""
        if self._index is None:
            start = _THOUGHT_START.match(self._raw)
            if start is None:
                return ""
            self._index = start.end()
        decoded: list[str] = []
        while self._index < len(self._raw) and not self._done:
            char, size = self._next_char()
            if size == 0:
                break  # an escape split between chunks
            decoded.append(char)
            self._index += size
        return "".join(decoded)

    def _next_char(self) -> tuple[str, int]:
        """Decode the character at the cursor: it and its raw size, 0 if cut off.

        The closing quote, or a malformed escape, ends the thought.
        """
        raw, index = self._raw, self._index or 0
        if raw[index] == '"':
            self._done = True
            return "", 0
        if raw[index] != "\\":
            return raw[index], 1
        if index + 1 >= len(raw):
            return "", 0
        if raw[index + 1] != "u":
            return _ESCAPES.get(raw[index + 1], raw[index + 1]), 2
        unit = _hex_unit(raw, index)
        if unit is None:
            return "", 0
        if not 0xD800 <= unit < 0xDC00:
            return chr(unit), 6
        low = _hex_unit(raw, index + 6)  # the second half of an emoji
        if low is None:
            return "", 0
        return chr(0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00)), 12


def _hex_unit(raw: str, index: int) -> int | None:
    """Read the `uXXXX` escape at `index`; `None` while it is incomplete."""
    digits = raw[index + 2 : index + 6]
    if len(digits) < 4:
        return None
    try:
        return int(digits, 16)
    except ValueError:
        return 0xFFFD  # not hexadecimal: shown as a replacement character
