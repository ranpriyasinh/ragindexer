"""Response schemas for comori-rag-indexer."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    embedding_provider: str
    embedding_dim: int


class KnowledgeChunkPayload(BaseModel):
    """Mirrors the `chunks[]` entries POSTed to comori-api's /api/knowledge/chunks."""

    chunkId: str
    source: str
    domain: str
    evidenceTier: str
    topicTags: List[str]
    content: str
    embedding: List[float]
    corpusVersion: str


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

class RetrieveResponse(BaseModel):
    type: str
    query: str
    k: int
    results: List[DecodedResult]
