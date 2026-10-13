"""Shared httpx helpers, injected into HTTP adapters by `app.py`."""

from sensai.adapters.http.auth import BearerAuth

__all__ = ["BearerAuth"]
