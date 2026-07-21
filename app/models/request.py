"""Request schemas for comori-rag-indexer."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class IngestType(str, Enum):
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"


class EvidenceTier(str, Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"


class Domain(str, Enum):
    NUTRITION = "nutrition"
    PHYSICAL_ACTIVITY = "physical_activity"
    SLEEP = "sleep"
    STRESS = "stress"
    METABOLIC_SCIENCE = "metabolic_science"
    LONGEVITY = "longevity"
    GENERAL = "general"


class MemoryKind(str, Enum):
    MESSAGE = "message"
    EVENT = "event"
    INTERVENTION = "intervention"
    FACT = "fact"


class KnowledgeIngestMetadata(BaseModel):
    """Metadata accompanying a knowledge (Branch A) file upload.

    Sent alongside the multipart file as a JSON-encoded form field named `metadata`.
    """

    source: str = Field(..., description='e.g. "Ben-Yacov 2021 · Diabetes Care"')
    domain: Domain
    evidence_tier: EvidenceTier
    topic_tags: List[str] = Field(default_factory=list)
    corpus_version: Optional[str] = None


class MemoryTurn(BaseModel):
    """A single PHI-scrubbed conversation snippet (Branch B)."""

    user_id: str
    kind: MemoryKind
    snippet: str = Field(..., description="PHI-scrubbed text content")
    ref: Optional[str] = Field(None, description='Reference id, e.g. "msg_..."')
    occurred_at: Optional[datetime] = None


class MemoryIngestRequest(BaseModel):
    """JSON body for Branch B ingestion (Type = memory)."""

    type: IngestType = IngestType.MEMORY
    turns: List[MemoryTurn]


class EmbedQueryRequest(BaseModel):
    query: str


class DecodeHit(BaseModel):
    """A single raw hit as returned by comori-api's similarity search."""

    id: str
    score: float
    content: str
    source: Optional[str] = None
    domain: Optional[str] = None
    evidence_tier: Optional[str] = None
    metadata: Optional[dict] = None


class DecodeRequest(BaseModel):
    hits: List[DecodeHit]

class RetrieveRequest(BaseModel):
    """Unified query-flow request: embed + search + decode in one call."""

    query: str = Field(..., min_length=1)
    type: IngestType = IngestType.KNOWLEDGE  # only KNOWLEDGE is implemented for now
    k: int = Field(default=5, ge=1, le=50)