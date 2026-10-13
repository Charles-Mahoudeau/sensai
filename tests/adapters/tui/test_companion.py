"""Tests for the companion's moods and frames, driven by a fake clock."""

from __future__ import annotations

import pytest
from rich.cells import cell_len

from sensai.adapters.tui.companion import (
    ANIMATIONS,
    FACE_WIDTH,
    SLEEP_AFTER,
    Companion,
    Mood,
)


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self) -> None:
        """Start at an arbitrary time."""
        self.now = 1000.0

    def __call__(self) -> float:
        """Tell the current time."""
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    """A fresh fake clock for the companion under test."""
    return FakeClock()


def test_frames_advance_with_the_interval(clock: FakeClock) -> None:
    """Each interval shows the next frame, looping at the end."""
    companion = Companion(clock)
    companion.set_mood(Mood.THINKING)
    animation = ANIMATIONS[Mood.THINKING]
    clock.now += animation.interval / 2  # sample mid-frame, away from rounding

    shown = []
    for _ in range(len(animation.frames) + 1):
        shown.append(companion.frame())
        clock.now += animation.interval

    assert shown == [*animation.frames, animation.frames[0]]


def test_setting_the_same_mood_keeps_the_animation_going(clock: FakeClock) -> None:
    """Streamed fragments re-set the mood without freezing it on frame one."""
    companion = Companion(clock)
    companion.set_mood(Mood.ANSWERING)
    clock.now += ANIMATIONS[Mood.ANSWERING].interval
    companion.set_mood(Mood.ANSWERING)

    assert companion.frame() == ANIMATIONS[Mood.ANSWERING].frames[1]


def test_flash_expires_back_to_the_base_mood(clock: FakeClock) -> None:
    """A flash shows its mood, then gives the base mood back."""
    companion = Companion(clock)
    companion.flash(Mood.HAPPY, 2.0)

    assert companion.mood is Mood.HAPPY

    clock.now += 2.0

    assert companion.mood is Mood.IDLE
    assert companion.frame() == ANIMATIONS[Mood.IDLE].frames[0]


def test_set_mood_cancels_a_flash(clock: FakeClock) -> None:
    """A new turn doesn't wait for the previous cheer to end."""
    companion = Companion(clock)
    companion.flash(Mood.HAPPY, 2.0)
    companion.set_mood(Mood.THINKING)

    assert companion.mood is Mood.THINKING


def test_falls_asleep_when_idle_and_poke_wakes_it(clock: FakeClock) -> None:
    """Nothing happening for a while sends it to sleep; a keystroke wakes it."""
    companion = Companion(clock)
    clock.now += SLEEP_AFTER

    assert companion.mood is Mood.ASLEEP
    assert companion.frame() == ANIMATIONS[Mood.ASLEEP].frames[0]

    companion.poke()

    assert companion.mood is Mood.IDLE


def test_never_sleeps_during_a_turn(clock: FakeClock) -> None:
    """A long thought is not idleness."""
    companion = Companion(clock)
    companion.set_mood(Mood.THINKING)
    clock.now += SLEEP_AFTER * 2

    assert companion.mood is Mood.THINKING


@pytest.mark.parametrize("mood", list(Mood))
def test_frames_keep_the_face_still(mood: Mood) -> None:
    """Every frame ends with a face of the same width, in single-width cells."""
    for frame in ANIMATIONS[mood].frames:
        assert cell_len(frame) == len(frame)
        face = frame[-FACE_WIDTH:]
        assert face.startswith("(")
        assert face.endswith(")")
