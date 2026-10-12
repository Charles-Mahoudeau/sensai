"""The companion: a small face in the prompt border that reacts to the app's state.

The face is always the last `FACE_WIDTH` cells of a frame, and props (dots,
notes, a spinner…) go on its left: the frame is drawn as a right-aligned border
title, so the face stays still while the props change width. Frames only use
single-width characters, so that the border never shifts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

FACE_WIDTH = 5
SLEEP_AFTER = 120.0


class Mood(StrEnum):
    """What the companion is showing."""

    IDLE = "idle"
    TYPING = "typing"
    THINKING = "thinking"
    ANSWERING = "answering"
    TOOL = "tool"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    HAPPY = "happy"
    ASLEEP = "asleep"


@dataclass(frozen=True, slots=True)
class Animation:
    """The frames of a mood, played in a loop."""

    frames: tuple[str, ...]
    interval: float  # seconds per frame


ANIMATIONS: dict[Mood, Animation] = {
    Mood.IDLE: Animation(("(•ᴗ•)",) * 15 + ("(-ᴗ-)",), 0.25),
    Mood.TYPING: Animation(("(•ᴗ•)", "(•ᴗ<)"), 0.6),
    Mood.THINKING: Animation(("(•_•)", ".(•_•)", "..(•_•)", "...(•_•)"), 0.4),
    Mood.ANSWERING: Animation(("(•o•)", "(•ᴗ•)", "(•O•)", "(•ᴗ•)"), 0.2),
    Mood.TOOL: Animation(("◐(•ᴗ•)", "◓(•ᴗ•)", "◑(•ᴗ•)", "◒(•ᴗ•)"), 0.2),
    Mood.ERROR: Animation(("(×_×)",), 1.0),  # noqa: RUF001 (dizzy eyes)
    Mood.INTERRUPTED: Animation(("!(°□°)",), 1.0),
    Mood.HAPPY: Animation(("♪(^ᴗ^)", "♫(^ᴗ^)"), 0.4),
    Mood.ASLEEP: Animation(("z(-_-)", "zZ(-_-)", "zZz(-_-)"), 0.8),
}


class Companion:
    """Picks the frame to show from a base mood, a passing flash and idle time.

    The base mood follows the turn (thinking, answering…). A flash shows another
    mood for a few seconds, then gives the base mood back. An idle companion
    falls asleep after `SLEEP_AFTER` seconds without activity.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Start idle, with `clock` telling the time in seconds."""
        self._clock = clock
        now = clock()
        self._base = Mood.IDLE
        self._since = now
        self._active = now
        self._flash: Mood | None = None
        self._flash_until = now

    @property
    def mood(self) -> Mood:
        """The mood shown right now."""
        return self._mood_at(self._clock())

    def set_mood(self, mood: Mood) -> None:
        """Switch the base mood, cancelling any flash, and count it as activity.

        Setting the mood already shown keeps its animation going, so that it can
        be called on every streamed fragment.
        """
        now = self._clock()
        self._active = now
        if self._flash is not None or mood is not self._base:
            self._since = now
        self._base = mood
        self._flash = None

    def flash(self, mood: Mood, seconds: float) -> None:
        """Show `mood` for `seconds`, then go back to the base mood."""
        now = self._clock()
        self._flash = mood
        self._flash_until = now + seconds
        self._since = now
        self._active = now

    def poke(self) -> None:
        """Record some activity, which wakes the companion up."""
        self._active = self._clock()

    def frame(self) -> str:
        """The frame to show right now."""
        now = self._clock()
        mood = self._mood_at(now)
        if mood is Mood.ASLEEP:
            start = self._active + SLEEP_AFTER
        elif self._flash is not None and now >= self._flash_until:
            start = self._flash_until
        else:
            start = self._since
        animation = ANIMATIONS[mood]
        index = int(max(0.0, now - start) / animation.interval)
        return animation.frames[index % len(animation.frames)]

    def _mood_at(self, now: float) -> Mood:
        if self._flash is not None and now < self._flash_until:
            return self._flash
        if self._base is Mood.IDLE and now - self._active >= SLEEP_AFTER:
            return Mood.ASLEEP
        return self._base
