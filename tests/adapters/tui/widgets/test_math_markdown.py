"""Tests for the Markdown widget that renders LaTeX math."""

from __future__ import annotations

import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets.markdown import MarkdownBlock

from sensai.adapters.tui.widgets import AssistantMessage
from sensai.adapters.tui.widgets.math_markdown import MarkdownMath, math_parser


def _inline(markdown: str) -> list[tuple[str, str]]:
    [_, inline, _] = math_parser().parse(markdown)
    return [(child.type, child.content) for child in inline.children or []]


@pytest.mark.parametrize("markdown", ["Soit $b=1$.", r"Soit \(b=1\)."])
def test_inline_math_is_flattened_and_emphasized(markdown: str) -> None:
    """Both inline delimiters give the Unicode formula, in italics."""
    assert _inline(markdown) == [
        ("text", "Soit "),
        ("em_open", ""),
        ("text", "b = 1"),
        ("em_close", ""),
        ("text", "."),
    ]


@pytest.mark.parametrize(
    "markdown",
    ["It costs $5 or $10.", "Use `$x$` in LaTeX.", "Not $ math $ here."],
)
def test_text_that_is_not_math_is_left_alone(markdown: str) -> None:
    """Prices, code spans and spaced dollars don't open a formula."""
    assert all(kind != "em_open" for kind, _ in _inline(markdown))


@pytest.mark.parametrize("markdown", ["$$\nx^2\n$$\n", "\\[ x^2 \\]\n"])
def test_display_math_is_a_block(markdown: str) -> None:
    """Both display delimiters give a block holding the Unicode formula."""
    [token] = math_parser().parse(markdown)

    assert token.type == "math_block"
    assert token.content.strip() == "x²"


class _Transcript(App[None]):
    def compose(self) -> ComposeResult:
        yield AssistantMessage()


def test_streamed_math_is_rendered_once_complete() -> None:
    """A formula split across fragments ends up flattened in the answer."""
    fragments = ["Soit $b", "=1$ et\n\n$$\n\\frac{a}", "{b}\n$$\n"]

    async def run() -> None:
        app = _Transcript()
        async with app.run_test() as pilot:
            message = app.query_one(AssistantMessage)
            for fragment in fragments:
                await message.add_fragment(fragment)
            await message.finish()
            await pilot.pause()

            [paragraph] = message.query("MarkdownParagraph").results(MarkdownBlock)
            [formula] = message.query(MarkdownMath)
            assert paragraph._content.plain == "Soit b = 1 et"
            assert formula._content.plain == "a/b"
            assert message.text == "".join(fragments)

    asyncio.run(run())
