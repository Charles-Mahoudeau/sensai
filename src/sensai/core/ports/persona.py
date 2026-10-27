"""Port for the personas the agent can take on."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sensai.core.errors import SensaiError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.persona import Persona


class PersonaError(SensaiError):
    """Base class for every error raised by a persona source."""


class PersonaNotFoundError(PersonaError):
    """No persona has the requested name."""


class PersonaInvalidError(PersonaError):
    """The persona exists but its content is not valid."""


class PersonaSource(Protocol):
    """Where personas come from.

    A source is read again on every call, so personas added or edited while
    the app runs are picked up without a restart.
    """

    def names(self) -> Sequence[str]:
        """Every persona available right now, sorted by name."""
        ...

    def load(self, name: str) -> Persona:
        """Read the current version of a persona.

        Raises:
            PersonaNotFoundError: No persona is called `name`.
            PersonaInvalidError: The persona exists but is not valid.
        """
        ...
