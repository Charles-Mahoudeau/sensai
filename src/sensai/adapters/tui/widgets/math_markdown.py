"""Markdown that shows LaTeX math as Unicode text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.texmath import texmath_plugin
from textual.content import Content
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownBlock

from sensai.adapters.tui.latex import latex_to_unicode

if TYPE_CHECKING:
    from markdown_it.rules_core import StateCore

INLINE_MATH = frozenset({"math_inline", "math_inline_double"})
BLOCK_MATH = frozenset({"math_block", "math_block_label", "math_block_eqno"})


def math_parser() -> MarkdownIt:
    r"""Build a GFM-like parser that also reads ``$``, ``$$``, ``\(`` and ``\[`` math.

    A ``$`` only opens math when followed by a non-space, and only closes it
    when preceded by one and not followed by a digit, so prices like
    "$5 or $10" stay plain text. Every formula is flattened to Unicode while
    parsing; inline ones are then rendered in italics, like regular emphasis.
    """
    parser = (
        MarkdownIt("gfm-like")
        .use(
            dollarmath_plugin,
            allow_space=False,
            allow_digits=False,
            double_inline=True,
        )
        .use(texmath_plugin, delimiters="brackets")
    )
    parser.core.ruler.push("unicode_math", _flatten_math)
    return parser


def _flatten_math(state: StateCore) -> None:
    """Convert every formula of the document to Unicode text."""
    for token in state.tokens:
        if token.type in BLOCK_MATH:
            token.content = latex_to_unicode(token.content)
        elif token.children:
            token.children = [
                flat for child in token.children for flat in _flatten_inline(child)
            ]


def _flatten_inline(token: Token) -> list[Token]:
    """Swap an inline formula for its Unicode text, emphasized."""
    if token.type not in INLINE_MATH:
        return [token]
    return [
        Token("em_open", "em", 1),
        Token("text", "", 0, content=latex_to_unicode(token.content)),
        Token("em_close", "em", -1),
    ]


class MarkdownMath(MarkdownBlock):
    """A displayed formula, on its own lines."""

    DEFAULT_CSS = """
    MarkdownMath {
        margin: 0 0 1 0;
        padding: 0 0 0 4;
        text-style: italic;
    }
    """

    def __init__(self, markdown: Markdown, token: Token) -> None:
        """Show the formula already flattened by `math_parser`."""
        super().__init__(markdown, token)
        self.set_content(Content(token.content.strip()))

    async def _update_from_block(self, block: MarkdownBlock) -> None:
        """Update in place while the formula streams in, instead of remounting."""
        if isinstance(block, MarkdownMath):
            self.set_content(block._content)
            self._copy_context(block)
        else:
            await super()._update_from_block(block)


class MathMarkdown(Markdown):
    """A Markdown document whose LaTeX formulas are shown as Unicode text."""

    def __init__(
        self, markdown: str | None = None, *, classes: str | None = None
    ) -> None:
        """Parse with `math_parser`."""
        super().__init__(markdown, classes=classes, parser_factory=math_parser)

    def unhandled_token(self, token: Token) -> MarkdownBlock | None:
        """Render displayed formulas, which plain Markdown doesn't know about."""
        if token.type in BLOCK_MATH:
            return MarkdownMath(self, token)
        return super().unhandled_token(token)
