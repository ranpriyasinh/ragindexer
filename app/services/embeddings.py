"""
Embedding provider abstraction.

OpenAI's `text-embedding-3-small` is the only active provider — 1536
dimensions, matching comori-api's pgvector `VECTOR(1536)` / HNSW cosine
schema. Code outside this module must never hardcode the dimension; always
read `.dimension` from the active provider instance.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List


class EmbeddingProvider(ABC):
    """Common interface every embedding backend must implement."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by this provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for the active provider, e.g. 'openai'."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns one vector per input text, in order."""

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class OpenAIProvider(EmbeddingProvider):
    """text-embedding-3-small / other OpenAI embedding models."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required to use the OpenAI embedding provider."
            )
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        # text-embedding-3-small = 1536 dims; kept dynamic rather than hardcoded
        # so a future model swap doesn't require code changes elsewhere.
        self._dimension = 1536 if "small" in self._model_name else 3072

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def name(self) -> str:
        return "openai"

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self._client.embeddings.create(model=self._model_name, input=texts)
        return [item.embedding for item in response.data]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Cached provider instance."""
    return OpenAIProvider()
