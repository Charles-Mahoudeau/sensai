"""httpx authentication schemes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Generator


class BearerAuth(httpx.Auth):
    """Sends `Authorization: Bearer <token>` with every request.

    httpx strips the header on cross-origin redirects, so the token never leaks
    to another host.
    """

    def __init__(self, token: str) -> None:
        """Create the auth.

        Args:
            token: The bearer token, without the `Bearer ` prefix.

        Raises:
            ValueError: The token is empty.
        """
        if not token:
            msg = "bearer token must not be empty"
            raise ValueError(msg)
        self._token = token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response]:
        """Add the bearer header to the request.

        Args:
            request: The outgoing request.

        Yields:
            The request with its `Authorization` header set.
        """
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

    def __repr__(self) -> str:
        """Hide the token so it never shows up in logs or tracebacks."""
        return "BearerAuth(token='***')"
