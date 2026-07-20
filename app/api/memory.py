"""
Branch B (memory) ingestion logic.

The single public HTTP route for ingestion is POST /api/v1/ingest, defined in
knowledge.py (spec section 2: "Unified Ingestion endpoint"). This module
provides `handle_memory_ingest`, which that unified endpoint calls when the
request body is JSON with `type: "memory"`.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.models.request import MemoryIngestRequest
from app.models.response import IngestSummary
from app.services.ingestion import IngestionService

# No routes are registered directly on this router today — it exists to keep
# memory-branch logic isolated per the fixed directory structure, and is
# reserved for future memory-only endpoints (e.g. per-user memory listing).
router = APIRouter(tags=["memory"])


def handle_memory_ingest(
    request: MemoryIngestRequest, ingestion_service: IngestionService
) -> IngestSummary:
    result = ingestion_service.ingest_memory_turns(request.turns)
    return IngestSummary(
        type="memory",
        memories_added=result["memories_added"],
        mode=ingestion_service._settings.COMORI_API_MODE,
        dispatched=result["dispatched"],
    )
