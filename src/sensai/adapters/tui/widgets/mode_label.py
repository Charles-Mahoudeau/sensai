"""The answer mode shown next to the persona, when it is not the default."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from sensai.core.agent.re_act import AgentMode

PLAN_LABEL = "Plan mode"


class ModeLabel(Static):
    """`Plan mode` in plan mode, hidden in the default mode."""

    DEFAULT_CSS = """
    ModeLabel {
        width: auto;
        padding: 0 3 0 0;
        color: $accent;
    }
    """

    def __init__(self, mode: AgentMode) -> None:
        """Show the given mode."""
        super().__init__(id="mode", markup=False)
        self.mode: AgentMode = mode
        self.set_mode(mode)

    def set_mode(self, mode: AgentMode) -> None:
        """Show another mode, or hide the label in the default one."""
        self.mode = mode
        self.display = mode == "plan"
        self.update(PLAN_LABEL if mode == "plan" else "")
