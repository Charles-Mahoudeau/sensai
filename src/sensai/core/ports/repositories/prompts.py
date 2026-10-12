"""Port for versioned prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sensai.core.ports.repositories.memory import StorageError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sensai.core.models.prompts import PromptVersion


class PromptNotFoundError(StorageError):
    """No version of the requested prompt is active."""


class PromptVersionNotFoundError(StorageError):
    """The requested version of a prompt does not exist."""


class PromptRepository(Protocol):
    """Saves every version of the named prompts and which one is active."""

    async def create_version(
        self, name: str, content: str, *, note: str | None = None
    ) -> PromptVersion:
        """Save a new version, numbered after the latest version of `name`.

        The new version is not activated.

        Raises:
            StorageError: The store failed to write.
        """
        ...

    async def get_version(self, name: str, version: int) -> PromptVersion:
        """Return one version.

        Raises:
            PromptVersionNotFoundError: `name` has no such version.
            StorageError: The store failed to read.
        """
        ...

    async def list_versions(self, name: str) -> Sequence[PromptVersion]:
        """Return every version of `name`, oldest first (empty if unknown).

        Raises:
            StorageError: The store failed to read.
        """
        ...

    async def find_by_content(self, name: str, content: str) -> PromptVersion | None:
        """Return the latest version of `name` with exactly this content, if any.

        Raises:
            StorageError: The store failed to read.
        """
        ...

    async def get_active(self, name: str) -> PromptVersion:
        """Return the active version of `name`.

        Raises:
            PromptNotFoundError: No version of `name` is active.
            StorageError: The store failed to read.
        """
        ...

    async def set_active(self, name: str, version: int) -> PromptVersion:
        """Make one version the active one and return it.

        Raises:
            PromptVersionNotFoundError: `name` has no such version.
            StorageError: The store failed to write.
        """
        ...

    async def list_active(self) -> Sequence[PromptVersion]:
        """Return the active version of every prompt, ordered by name.

        Raises:
            StorageError: The store failed to read.
        """
        ...
