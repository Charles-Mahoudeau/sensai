"""Checks that keep a new prompt version usable by the code that formats it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from string import Formatter

from sensai.core.errors import SensaiError
from sensai.core.prompts.defaults import REACT_NOTES, REACT_THOUGHT


class InvalidPromptError(SensaiError, ValueError):
    """A prompt version would break the code that uses it."""


@dataclass(frozen=True, slots=True)
class PromptRule:
    """What a templated prompt must contain.

    Attributes:
        placeholders: The `str.format` fields the code fills in; a version must
            use all of them and no other.
        required_text: Phrases the code relies on, matched ignoring case.
    """

    placeholders: frozenset[str] = frozenset()
    required_text: tuple[str, ...] = ()


PROMPT_RULES: dict[str, PromptRule] = {
    REACT_THOUGHT: PromptRule(frozenset({"tools"}), ("ready to answer",)),
    REACT_NOTES: PromptRule(frozenset({"thought"})),
}

_FIELD_ROOT = re.compile(r"[.\[]")


def validate(name: str, content: str) -> None:
    """Check `content` against the rule of prompt `name`, if it has one.

    Raises:
        InvalidPromptError: A placeholder is missing, unknown or malformed, or a
            required phrase is missing.
    """
    rule = PROMPT_RULES.get(name)
    if rule is None:
        return
    try:
        fields = {
            _FIELD_ROOT.split(field, maxsplit=1)[0]
            for _, field, _, _ in Formatter().parse(content)
            if field is not None
        }
    except ValueError as error:
        raise InvalidPromptError(
            f"prompt {name!r} has malformed braces ({error}); "
            "write literal braces as {{ and }}"
        ) from None
    if missing := rule.placeholders - fields:
        raise InvalidPromptError(
            f"prompt {name!r} must contain {_placeholders(missing)}"
        )
    if unknown := fields - rule.placeholders:
        raise InvalidPromptError(
            f"prompt {name!r} has unknown {_placeholders(unknown)}; "
            f"allowed: {_placeholders(rule.placeholders)}"
        )
    for phrase in rule.required_text:
        if phrase.lower() not in content.lower():
            raise InvalidPromptError(f"prompt {name!r} must contain {phrase!r}")


def _placeholders(names: frozenset[str] | set[str]) -> str:
    return ", ".join(f"{{{name}}}" for name in sorted(names)) or "none"
