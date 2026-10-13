"""The thinking effort shown next to the prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.color import Color
from textual.content import Content
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.timer import Timer

    from sensai.core.models import ThinkingEffort


NO_THINKING_COLOR = "#ff8a65"
RAINBOW_INTERVAL = 0.08
RAINBOW_HUE_STEP = 0.07
RAINBOW_HUE_SPEED = 0.04


class EffortLabel(Static):
    """The thinking effort, right-aligned; Ultra is animated in rainbow colors."""

    DEFAULT_CSS = """
    EffortLabel {
        width: auto;
        padding: 0 3 0 0;
        color: $text-muted;
    }
    """

    def __init__(self, effort: ThinkingEffort) -> None:
        """Show the given effort."""
        super().__init__(id="effort", markup=False)
        self.effort = effort
        self._phase = 0.0
        self._rainbow_timer: Timer | None = None

    def set_effort(self, effort: ThinkingEffort) -> None:
        """Show another effort, animating it only when it is Ultra."""
        self.effort = effort
        self._stop_animation()
        if effort.name == "ULTRA":
            self._phase = 0.0
            self._rainbow_timer = self.set_interval(
                RAINBOW_INTERVAL, self._tick_rainbow
            )
            self._tick_rainbow()
        elif effort.name == "NONE":
            self.update(Content.assemble((effort.label, NO_THINKING_COLOR)))
        else:
            self.update(effort.label)

    def _tick_rainbow(self) -> None:
        self._phase = (self._phase + RAINBOW_HUE_SPEED) % 1.0
        label = self.effort.label
        self.update(
            Content.assemble(
                *(
                    (
                        char,
                        Color.from_hsl(
                            (self._phase + index * RAINBOW_HUE_STEP) % 1.0, 0.9, 0.6
                        ).hex,
                    )
                    for index, char in enumerate(label)
                )
            )
        )

    def _stop_animation(self) -> None:
        if self._rainbow_timer is not None:
            self._rainbow_timer.stop()
            self._rainbow_timer = None
