"""
Query-side helpers: query embedding + decode/formatting of raw hits.

Per spec section 2 (Query Flow):
1. comori-va calls POST /api/v1/embed/query on this service to embed a query.
2. comori-va -> comori-api performs the actual HNSW similarity search (not here).
3. comori-va sends raw hits back to POST /api/v1/decode for formatting/cleanup.
"""
from __future__ import annotations

import re
from typing import List

from app.services.embeddings import EmbeddingProvider
from schema.request import DecodeHit
from schema.response import DecodedResult


def embed_query(provider: EmbeddingProvider, query: str) -> List[float]:
    return provider.embed_one(query)


_WHITESPACE_RE = re.compile(r"\s+")


def decode_hits(hits: List[DecodeHit]) -> List[DecodedResult]:
    """Clean raw retrieval hits into presentation-ready text.

    This does NOT re-rank or filter — comori-api owns ranking. It only
    normalizes whitespace/formatting artifacts from stored chunk content.
    """
    results: List[DecodedResult] = []
    for hit in hits:
        cleaned = _WHITESPACE_RE.sub(" ", hit.content).strip()
        results.append(
            DecodedResult(
                id=hit.id,
                text=cleaned,
                source=hit.source,
                domain=hit.domain,
                evidence_tier=hit.evidence_tier,
                score=hit.score,
            )
        )
    return results
