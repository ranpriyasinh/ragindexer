"""
Embedding provider abstraction.

Per spec instruction 2 ("Decouple Providers"): code outside this module must
never assume a fixed vector dimension. Always read `.dimension` from the
active provider instance instead of hardcoding 384 / 1536 elsewhere.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List

from app.config import Settings, get_settings


class EmbeddingProvider(ABC):
    """Common interface every embedding backend must implement."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by this provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for the active provider, e.g. 'minilm'."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns one vector per input text, in order."""

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class MiniLMProvider(EmbeddingProvider):
    """Local all-MiniLM-L6-v2 via sentence-transformers. 384-dim, active provider."""

    MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self) -> None:
        # Imported lazily so the module can be imported without the (heavy)
        # sentence-transformers dependency installed, e.g. during unit tests
        # that stub out the provider.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.MODEL_NAME)
        self._dimension = self._model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def name(self) -> str:
        return "minilm"

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]


class OpenAIProvider(EmbeddingProvider):
    """
    text-embedding-3-small / other OpenAI embedding models.

    DISABLED by default per spec section 4 — EMBEDDING_PROVIDER must be
    explicitly set to "openai" and OPENAI_API_KEY must be configured.
    Left implemented so switching providers later doesn't require touching
    any caller of EmbeddingProvider.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is required to use the openai embedding provider."
            )
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model_name = settings.OPENAI_EMBEDDING_MODEL
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
    """Cached provider instance selected via EMBEDDING_PROVIDER."""
    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "minilm":
        return MiniLMProvider()
    if settings.EMBEDDING_PROVIDER == "openai":
        return OpenAIProvider(settings)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}")
