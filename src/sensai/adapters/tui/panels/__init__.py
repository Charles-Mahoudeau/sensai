"""Small panels opened by slash commands in place of the prompt."""

from sensai.adapters.tui.panels.base import Panel
from sensai.adapters.tui.panels.mcp import McpPanel
from sensai.adapters.tui.panels.tools import ToolsPanel
from sensai.adapters.tui.panels.usage import UsagePanel

__all__ = ["McpPanel", "Panel", "ToolsPanel", "UsagePanel"]
