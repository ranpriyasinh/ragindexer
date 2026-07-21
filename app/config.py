"""
Configuration for comori-rag-indexer.

All values are sourced from environment variables / .env file.
See spec section 4 (Configuration & Modes).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Embedding provider -------------------------------------------------
    # "minilm" is the only active provider today (all-MiniLM-L6-v2, 384 dim).
    # OpenAI provider config is present but intentionally left disabled.
    EMBEDDING_PROVIDER: Literal["minilm", "openai"] = "minilm"

    # OpenAI provider config — kept for future use, disabled by default.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- comori-api integration mode ----------------------------------------
    # "print": log the outbound payload to stdout instead of making a network call.
    # "http": POST the payload to COMORI_API_URL.
    COMORI_API_MODE: Literal["print", "http"] = "print"
    COMORI_API_URL: Optional[str] = None
    COMORI_API_KEY: Optional[str] = None

    # --- Chunking -------------------------------------------------------------
    CHUNK_TOKEN_SIZE: int = 400
    CHUNK_TOKEN_OVERLAP: int = 50

    # --- Corpus -----------------------------------------------------------
    CORPUS_VERSION: str = "v0.1.0"

    # --- App ----------------------------------------------------------------
    APP_NAME: str = "comori-rag-indexer"
    HTTP_TIMEOUT_SECONDS: float = 15.0

    # --- PostgreSQL Connection -----------------------------------------------
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "comori_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — import this everywhere instead of instantiating Settings()."""
    return Settings()
