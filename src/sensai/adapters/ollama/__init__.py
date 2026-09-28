"""Adapter for the Ollama HTTP API."""

from sensai.adapters.ollama.chat import OllamaChat
from sensai.adapters.ollama.embed import DEFAULT_EMBED_MODEL, OllamaEmbedder

__all__ = ["DEFAULT_EMBED_MODEL", "OllamaChat", "OllamaEmbedder"]
