r"""Turn LaTeX math into plain Unicode text a terminal can show.

A terminal can't typeset math, so formulas are flattened: symbols become their
Unicode characters (``\alpha``, ``\leq``, ``\mathbb{R}``…), short scripts use
the Unicode super- and subscript letters (``x^2`` → ``x²``), and fractions and
roots are written inline (``\frac{a+b}{2}`` → ``(a+b)/2``).
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any

from pylatexenc.latex2text import (
    LatexNodes2Text,
    MacroTextSpec,
    SpecialsTextSpec,
)
from pylatexenc.latex2text import (
    get_default_latex_context_db as text_context,
)
from pylatexenc.latexwalker import LatexWalker
from pylatexenc.latexwalker import (
    get_default_latex_context_db as parse_context,
)
from pylatexenc.macrospec import MacroStandardArgsParser, SpecialsSpec

if TYPE_CHECKING:
    from collections.abc import Callable

    from pylatexenc.latexwalker import LatexMacroNode, LatexNode, LatexSpecialsNode

    type Node = LatexMacroNode | LatexSpecialsNode

SUPERSCRIPTS = str.maketrans(
    "0123456789+-=()abcdefghijklmnoprstuvwxyz",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ",
)
SUBSCRIPTS = str.maketrans(
    "0123456789+-=()aehijklmnoprstuvx",
    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ",
)

FUNCTIONS = ("lim", "sin", "cos", "tan", "log", "ln", "exp", "max", "min", "det")
"""Operator names written upright, which pylatexenc doesn't know about."""

RELATIONS = "=<>≤≥≠≈≡∼≃≅∝→←↔⇒⇐⇔↦∈∉⊂⊃⊆⊇∣×÷±∓"  # noqa: RUF001
"""Symbols that get a space on each side, however the source spaced them."""

_AROUND_RELATION = re.compile(rf"\s*([{RELATIONS}])\s*")
_INSIDE_BRACKETS = re.compile(r"([(\[{])\s+|\s+([)\]}])")
_SPACES = re.compile(r"[ \t]+")


def latex_to_unicode(latex: str) -> str:
    r"""Flatten a LaTeX formula into Unicode text.

    Incomplete or invalid LaTeX, as seen mid-stream, gives a best-effort
    result rather than an error.

    Args:
        latex: The formula, without its ``$`` or ``\(`` delimiters.

    Returns:
        The formula as plain text.
    """
    try:
        walker = LatexWalker(
            latex, latex_context=_parse_context(), tolerant_parsing=True
        )
        nodes, _, _ = walker.get_latex_nodes()
        text = _converter().nodelist_to_text(nodes)
    except Exception:  # a formula must never break the transcript
        return latex
    text = _AROUND_RELATION.sub(r" \1 ", text)
    text = _INSIDE_BRACKETS.sub(r"\1\2", text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


@cache
def _parse_context() -> Any:
    """Read ``^`` and ``_`` as taking one argument, like in math mode."""
    context = parse_context()
    script = MacroStandardArgsParser("{")
    context.add_context_category(
        "sensai-scripts",
        specials=[SpecialsSpec("^", script), SpecialsSpec("_", script)],
        prepend=True,
    )
    return context


@cache
def _converter() -> LatexNodes2Text:
    """The pylatexenc converter, taught scripts, fractions and operator names."""
    context = text_context()
    context.add_context_category(
        "sensai-math",
        macros=[
            *(
                MacroTextSpec(name, simplify_repl=_fraction)
                for name in ("frac", "dfrac", "tfrac")
            ),
            *(MacroTextSpec(name, simplify_repl=name) for name in FUNCTIONS),
            MacroTextSpec("sqrt", simplify_repl=_root),
            MacroTextSpec("mid", simplify_repl="∣"),  # noqa: RUF001
        ],
        specials=[
            SpecialsTextSpec("^", simplify_repl=_script(SUPERSCRIPTS, "^")),
            SpecialsTextSpec("_", simplify_repl=_script(SUBSCRIPTS, "_")),
        ],
        prepend=True,
    )
    return LatexNodes2Text(
        latex_context=context,
        math_mode="text",
        strict_latex_spaces="based-on-source",
    )


def _script(table: dict[int, int], marker: str) -> Callable[..., str]:
    """Render a ``^``/``_`` script with Unicode letters, or spelled out if it can't.

    pylatexenc passes the converter in by keyword, under the name ``l2tobj``.
    """

    def render(node: Node, l2tobj: LatexNodes2Text) -> str:
        [argument] = _arguments(node, 1)
        if argument is None:
            return marker
        text = "".join(l2tobj.nodelist_to_text([argument]).split())
        if text and all(ord(char) in table for char in text):
            return text.translate(table)
        return marker + (text if len(text) == 1 else f"({text})")

    return render


def _fraction(node: Node, l2tobj: LatexNodes2Text) -> str:
    """Write a fraction inline, bracketing a numerator or denominator if needed."""
    arguments = _arguments(node, 2)
    if None in arguments:
        return ""
    numerator, denominator = (
        l2tobj.nodelist_to_text([argument]).strip() for argument in arguments
    )
    if not numerator.isalnum():
        numerator = _grouped(numerator)
    return f"{numerator}/{_grouped(denominator)}"


def _root(node: Node, l2tobj: LatexNodes2Text) -> str:
    """Write a root as ``√``, with its index as a superscript if it has one."""
    index, radicand = _arguments(node, 2)
    if radicand is None:
        return "√"
    degree = "" if index is None else l2tobj.nodelist_to_text([index]).strip()
    text = l2tobj.nodelist_to_text([radicand]).strip()
    return f"{degree.translate(SUPERSCRIPTS)}√{_grouped(text)}"


def _arguments(node: Node, count: int) -> list[LatexNode | None]:
    """The last ``count`` arguments of ``node``, with `None` for each missing one."""
    parsed = node.nodeargd
    arguments = [] if parsed is None else list(parsed.argnlist[-count:])
    return [None] * (count - len(arguments)) + arguments


def _grouped(text: str) -> str:
    """Bracket ``text`` unless it is a single symbol or a number."""
    return text if len(text) <= 1 or text.isdigit() else f"({text})"
