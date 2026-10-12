"""The /tools panel: list the tools and enable or disable them."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Horizontal
from textual.content import Content
from textual.widgets import Button, Input, OptionList
from textual.widgets.option_list import Option

from sensai.adapters.tui.panels.base import Panel

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import BindingType

    from sensai.core.engine import Engine
    from sensai.core.models import ToolInfo

HINTS = "↑↓ move · space toggle · ^a/^d all · esc close"
NO_TOOLS_TEXT = "No tools"
NO_MATCH_TEXT = "No tools match"


class ToolList(OptionList):
    """The tools, grouped by source; the filter input keeps the focus."""

    can_focus = False


class ToolFilter(Input):
    """The filter input; space toggles the highlighted tool instead of typing."""

    def check_consume_key(self, key: str, character: str | None) -> bool:
        """Leave space to the panel's toggle binding."""
        return key != "space" and super().check_consume_key(key, character)


class ToolsPanel(Panel):
    """List every tool, toggle one, or enable or disable those shown.

    The filter input keeps the focus: typing narrows the list to the tools
    whose name or description contains the text, and Enable/Disable all then
    only apply to the tools shown.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Previous tool", show=False),
        Binding("down", "move(1)", "Next tool", show=False),
        # priority: the filter input binds enter and ctrl+a/d itself
        Binding("space,enter", "toggle_tool", "Toggle", show=False, priority=True),
        Binding("ctrl+a", "set_shown(True)", "Enable all", show=False, priority=True),
        Binding("ctrl+d", "set_shown(False)", "Disable all", show=False, priority=True),
    ]

    def __init__(self, engine: Engine) -> None:
        """Show and toggle the tools of `engine`."""
        super().__init__(id="tools-panel", classes="panel")
        self._engine = engine
        self._filter = ""

    def compose(self) -> ComposeResult:
        """Lay out the filter and the buttons on one line, then the list.

        The counts go in the top border and the key hints in the bottom one,
        so that the list keeps most of the room in a small window.
        """
        with Horizontal(id="tools-header"):
            yield ToolFilter(
                placeholder="Filter tools…", id="tools-filter", compact=True
            )
            yield Button("Enable all", id="tools-enable", compact=True)
            yield Button("Disable all", id="tools-disable", compact=True)
        yield ToolList(id="tools-list")

    def on_mount(self) -> None:
        """List the tools; the buttons are clicked, never focused."""
        for button in self.query(Button):
            button.can_focus = False
        self.border_subtitle = HINTS
        self._refresh()

    def focus_first(self) -> None:
        """Focus the filter, so typing narrows the list."""
        self.query_one("#tools-filter", Input).focus()

    @property
    def shown(self) -> list[ToolInfo]:
        """The tools matching the filter, in registration order."""
        return [tool for tool in self._engine.tools() if self._matches(tool)]

    def on_input_changed(self, event: Input.Changed) -> None:
        """Narrow the list to the tools matching the new filter."""
        event.stop()
        self._filter = event.value.strip().lower()
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Enable or disable the tools shown."""
        event.stop()
        self.action_set_shown(enabled=event.button.id == "tools-enable")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Toggle a clicked tool."""
        event.stop()
        if event.option.id is not None:
            self._toggle(event.option.id)

    def action_move(self, step: int) -> None:
        """Highlight the previous or next tool, skipping the source headers."""
        tools = self.query_one(ToolList)
        if step < 0:
            tools.action_cursor_up()
        else:
            tools.action_cursor_down()

    def action_toggle_tool(self) -> None:
        """Enable the highlighted tool if it is disabled, or disable it."""
        tools = self.query_one(ToolList)
        if tools.highlighted is None:
            return
        name = tools.get_option_at_index(tools.highlighted).id
        if name is not None:
            self._toggle(name)

    def action_set_shown(self, enabled: bool) -> None:
        """Enable or disable every tool shown; all of them when not filtered."""
        names = None if not self._filter else [tool.spec.name for tool in self.shown]
        self._engine.set_tools_enabled(enabled=enabled, names=names)
        self._refresh()

    def _toggle(self, name: str) -> None:
        tool = next(tool for tool in self._engine.tools() if tool.spec.name == name)
        self._engine.set_tool_enabled(name, enabled=not tool.enabled)
        self._refresh()

    def _matches(self, tool: ToolInfo) -> bool:
        return (
            self._filter in tool.spec.name.lower()
            or self._filter in tool.spec.description.lower()
        )

    def _refresh(self) -> None:
        """Redraw the counts and the list, keeping the highlighted tool."""
        every = self._engine.tools()
        shown = self.shown
        enabled = sum(tool.enabled for tool in every)
        title = f"Tools · {enabled}/{len(every)} enabled"
        if self._filter:
            title += f" · {len(shown)} shown"
        self.border_title = Content(title)
        scope = "shown" if self._filter else "all"
        self.query_one("#tools-enable", Button).label = f"Enable {scope}"
        self.query_one("#tools-disable", Button).label = f"Disable {scope}"

        tools = self.query_one(ToolList)
        kept = tools.highlighted_option.id if tools.highlighted_option else None
        tools.clear_options()
        tools.add_options(_options(every, shown))
        names = [tool.spec.name for tool in shown]
        target = kept if kept in names else (names[0] if names else None)
        tools.highlighted = (
            tools.get_option_index(target) if target is not None else None
        )


def _options(every: tuple[ToolInfo, ...], shown: list[ToolInfo]) -> list[Option]:
    """Group the tools shown by source, each under a header counting its tools."""
    if not shown:
        return [Option(NO_MATCH_TEXT if every else NO_TOOLS_TEXT, disabled=True)]
    width = max(len(tool.short_name) for tool in shown)
    options: list[Option] = []
    for source in dict.fromkeys(tool.source for tool in shown):
        group = [tool for tool in every if tool.source == source]
        enabled = sum(tool.enabled for tool in group)
        options.append(
            Option(Content(f"── {source} · {enabled}/{len(group)} ──"), disabled=True)
        )
        options.extend(
            Option(_row(tool, width), id=tool.spec.name)
            for tool in shown
            if tool.source == source
        )
    return options


def _row(tool: ToolInfo, width: int) -> Content:
    box = ("[x] ", "$success") if tool.enabled else ("[ ] ", "dim")
    name = (tool.short_name.ljust(width), "bold" if tool.enabled else "dim")
    return Content.assemble(box, name, "  ", (_summary(tool), "dim"))


def _summary(tool: ToolInfo) -> str:
    """The description's first line; the list cuts it at its own width."""
    return tool.spec.description.strip().partition("\n")[0]
