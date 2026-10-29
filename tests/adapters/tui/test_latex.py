"""Tests for flattening LaTeX math into Unicode text."""

from __future__ import annotations

import pytest

from sensai.adapters.tui.latex import latex_to_unicode


@pytest.mark.parametrize(
    ("latex", "text"),
    [
        (r"b=1", "b = 1"),
        (r"x^2 + y^{10} = z_1", "x² + y¹⁰ = z₁"),
        (r"e^{-x}", "e⁻ˣ"),
        (r"e^{i\pi}", "e^(iπ)"),
        (r"\alpha \leq \beta", "α ≤ β"),  # noqa: RUF001
        (r"\mathbb{R}^n \to \mathbb{R}", "ℝⁿ → ℝ"),  # noqa: RUF001
        (r"\frac{a+b}{2}", "(a+b)/2"),
        (r"x = \frac{-b \pm \sqrt{\Delta}}{2a}", "x = (-b ± √Δ)/(2a)"),
        (r"\sqrt{x^2+1}", "√(x²+1)"),
        (r"\sqrt[3]{8}", "³√8"),
        (r"\cos^2\theta + \sin^2\theta = 1", "cos²θ + sin²θ = 1"),
        (r"\left( \frac{1}{2} \right)", "(1/2)"),
        (r"\text{if } x \neq 0", "if x ≠ 0"),
    ],
)
def test_formulas_are_flattened(latex: str, text: str) -> None:
    """Symbols, scripts, fractions and roots turn into readable Unicode."""
    assert latex_to_unicode(latex) == text


def test_line_breaks_are_kept() -> None:
    r"""Each ``\\`` row of an aligned formula stays on its own line."""
    latex = r"\begin{aligned} a &= b \\ c &= d \end{aligned}"

    assert latex_to_unicode(latex) == "a = b\nc = d"


@pytest.mark.parametrize("latex", [r"\frac{x", r"x^", r"\sqrt", r"\left(", "{"])
def test_incomplete_formulas_do_not_raise(latex: str) -> None:
    """A formula cut mid-stream still gives some text."""
    assert isinstance(latex_to_unicode(latex), str)
