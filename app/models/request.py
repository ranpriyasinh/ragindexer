"""Request schemas for comori-rag-indexer."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


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
    """Metadata accompanying a knowledge (Branch A) ingest request."""

    source: str = Field(..., description='e.g. "Ben-Yacov 2021 · Diabetes Care"')
    domain: Domain
    evidence_tier: EvidenceTier
    topic_tags: List[str] = Field(default_factory=list)
    corpus_version: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_metadata_case(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if isinstance(data.get("domain"), str):
                data["domain"] = data["domain"].lower()
            if isinstance(data.get("evidence_tier"), str):
                data["evidence_tier"] = data["evidence_tier"].lower()
        return data


class KnowledgeIngestRequest(BaseModel):
    """JSON body for Branch A ingestion (Type = knowledge).

    Text is expected to already be extracted (e.g. from a PDF/MD) upstream —
    this service no longer parses files, only chunks + embeds + pushes.
    Supports both flat camelCase payloads and nested metadata payloads.
    """

    type: Optional[IngestType] = IngestType.KNOWLEDGE
    text: str = Field(..., min_length=1, description="Already-extracted document text.")
    metadata: KnowledgeIngestMetadata

    @model_validator(mode="before")
    @classmethod
    def normalize_flat_or_nested(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "metadata" not in data or not data["metadata"]:
                source = data.get("source") or "Unknown Source"
                raw_domain = data.get("domain")
                raw_tier = data.get("evidenceTier") or data.get("evidence_tier")
                raw_tags = data.get("topicTags") or data.get("topic_tags") or []
                raw_version = data.get("corpusVersion") or data.get("corpus_version")

                if isinstance(raw_domain, str):
                    raw_domain = raw_domain.lower()
                if isinstance(raw_tier, str):
                    raw_tier = raw_tier.lower()

                data["metadata"] = {
                    "source": source,
                    "domain": raw_domain or "general",
                    "evidence_tier": raw_tier or "tier3",
                    "topic_tags": raw_tags,
                    "corpus_version": raw_version,
                }
            if "type" not in data or not data["type"]:
                data["type"] = "knowledge"
        return data


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
    type: IngestType = IngestType.KNOWLEDGE
    k: int = Field(default=5, ge=1, le=50)
    user_id: Optional[str] = None