"""The /usage panel: the session's tokens, the context fill and the model memory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.content import Content
from textual.widgets import Static

from sensai.adapters.tui.panels.base import Panel

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from sensai.core.models.llm import LoadedModel, UsageReport

HINTS = "esc close"
_LABEL_WIDTH = 10
_GIB = 1024**3


class UsagePanel(Panel):
    """Show a usage report taken when the panel was opened."""

    def __init__(self, report: UsageReport) -> None:
        """Show `report`; it is not refreshed while the panel is open."""
        super().__init__(id="usage-panel", classes="panel")
        self._report = report

    def compose(self) -> ComposeResult:
        """Lay out one titled block per topic; the hints go in the border."""
        self.border_title = Content("Usage")
        self.border_subtitle = HINTS
        for title, rows in (
            ("Session", _session_rows(self._report)),
            ("Context", _context_rows(self._report)),
            ("Memory", _memory_rows(self._report)),
        ):
            yield Static(Content.styled(title, "bold"), classes="usage-title")
            for row in rows:
                yield Static(row, classes="usage-row")


def _row(label: str, *value: str | tuple[str, str]) -> Content:
    return Content.assemble((label.ljust(_LABEL_WIDTH), "dim"), *value)


def _session_rows(report: UsageReport) -> list[Content]:
    usage = report.session
    speed = usage.completion_tokens_per_second
    calls = f"{usage.calls:,} {'call' if usage.calls == 1 else 'calls'} to the model"
    return [
        _row(
            "Tokens",
            f"{usage.total_tokens:,} total",
            (
                f"   {usage.prompt_tokens:,} prompt · "
                f"{usage.completion_tokens:,} completion",
                "dim",
            ),
        ),
        _row("Calls", calls if speed is None else f"{calls} · {speed:.1f} tok/s"),
    ]


def _context_rows(report: UsageReport) -> list[Content]:
    rows = [_used_row(report)]
    if window := _window_row(report):
        rows.append(window)
    return rows


def _used_row(report: UsageReport) -> Content:
    ratio = report.context_ratio
    if ratio is not None:
        style = "$error" if ratio >= 0.9 else "$warning" if ratio >= 0.7 else ""
        return _row(
            "Used",
            (f"{report.context_used:,} / {report.context_limit:,}", style),
            (f"   {ratio:.0%}", style or "dim"),
        )
    if report.context_used is None:
        reason = "unknown until the next answer"
    else:
        reason = f"{report.context_used:,} tokens, window size unknown"
    return _row("Used", (reason, "dim italic"))


def _window_row(report: UsageReport) -> Content | None:
    loaded, most = report.context_limit, report.context_max
    if loaded is not None and most is not None:
        return _row("Window", f"{loaded:,} loaded", (f"   {most:,} max", "dim"))
    if most is not None:
        return _row("Window", (f"{most:,} max", "dim"))
    if loaded is not None:
        return _row("Window", f"{loaded:,} loaded")
    return None


def _memory_rows(report: UsageReport) -> list[Content]:
    model = report.loaded_model
    if report.monitor_error is not None:
        return [_row("Status", ("unavailable: ", "$error"), report.monitor_error)]
    if model is None:
        return [_row("Status", ("model not loaded right now", "dim italic"))]
    return [
        _row("Model", model.name),
        _row("VRAM", _size(model.vram_bytes)),
        _ram_row(model),
    ]


def _ram_row(model: LoadedModel) -> Content:
    if model.fully_on_gpu:
        return _row("RAM", ("none, fully on GPU", "dim"))
    return _row(
        "RAM",
        (_size(model.ram_bytes), "$warning"),
        ("   spilled from the GPU, slower", "$warning"),
    )


def _size(size_bytes: int) -> str:
    return f"{size_bytes / _GIB:.1f} GiB"
