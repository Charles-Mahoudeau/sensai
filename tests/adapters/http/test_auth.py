"""Tests for BearerAuth, using httpx.MockTransport instead of a real server."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from sensai.adapters.http import BearerAuth


def _echo_auth_header(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=request.headers.get("Authorization", ""))


def test_bearer_auth_sets_header_sync() -> None:
    """A sync client sends the bearer header."""
    transport = httpx.MockTransport(_echo_auth_header)
    with httpx.Client(transport=transport, auth=BearerAuth("s3cret")) as client:
        assert client.get("https://example.test").text == "Bearer s3cret"


def test_bearer_auth_sets_header_async() -> None:
    """An async client sends the bearer header."""

    async def run() -> str:
        transport = httpx.MockTransport(_echo_auth_header)
        async with httpx.AsyncClient(
            transport=transport, auth=BearerAuth("s3cret")
        ) as client:
            return (await client.get("https://example.test")).text

    assert asyncio.run(run()) == "Bearer s3cret"


def test_bearer_auth_rejects_empty_token() -> None:
    """An empty token is refused up front."""
    with pytest.raises(ValueError, match="must not be empty"):
        BearerAuth("")


def test_bearer_auth_repr_hides_token() -> None:
    """The token never appears in the repr."""
    assert "s3cret" not in repr(BearerAuth("s3cret"))
