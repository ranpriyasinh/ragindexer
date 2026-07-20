"""Response schemas for comori-rag-indexer."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    embedding_provider: str
    embedding_dim: int
    comori_api_mode: str


class KnowledgeChunkPayload(BaseModel):
    """Mirrors the knowledge_chunks table (spec section 3)."""

    chunk_id: str
    source: str
    domain: str
    evidence_tier: str
    topic_tags: List[str]
    content: str
    embedding: List[float]
    corpus_version: str


class MemoryVectorPayload(BaseModel):
    """Mirrors the memory_vectors table (spec section 3)."""

    memory_id: str
    user_id: str
    kind: str
    snippet: str
    ref: Optional[str] = None
    embedding: List[float]
    occurred_at: Optional[str] = None


class IngestSummary(BaseModel):
    """Structured summary returned after an ingest call."""

    type: str
    docs_processed: int = 0
    chunks_added: int = 0
    chunks_updated: int = 0
    chunks_skipped: int = 0
    memories_added: int = 0
    mode: str
    dispatched: bool


class EmbedQueryResponse(BaseModel):
    embedding: List[float]
    dim: int
    provider: str


class DecodedResult(BaseModel):
    id: str
    text: str
    source: Optional[str] = None
    domain: Optional[str] = None
    evidence_tier: Optional[str] = None
    score: float


class DecodeResponse(BaseModel):
    results: List[DecodedResult]
