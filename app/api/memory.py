"""
Branch B (memory) ingestion logic.

The single public HTTP route for ingestion is POST /api/v1/ingest, defined in
knowledge.py (spec section 2: "Unified Ingestion endpoint"). This module
provides `handle_memory_ingest`, which that unified endpoint calls when the
request body is JSON with `type: "memory"`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.memory_ingestion import MemoryIngestionError, MemoryIngestionService
from schema.request import MemoryIngestRequest
from schema.response import IngestSummary

# No routes are registered directly on this router today — it exists to keep
# memory-branch logic isolated per the fixed directory structure, and is
# reserved for future memory-only endpoints (e.g. per-user memory listing).
router = APIRouter(tags=["memory"])


def get_memory_ingestion_service() -> MemoryIngestionService:
    return MemoryIngestionService()


def handle_memory_ingest(
    request: MemoryIngestRequest,
    ingestion_service: Any = None,
) -> IngestSummary:
    """
    Handles JSON Branch B memory turn ingestion.
    Uses dedicated MemoryIngestionService for PHI validation, vectorization, and dispatch.
    """
    if isinstance(ingestion_service, MemoryIngestionService):
        service = ingestion_service
    else:
        service = get_memory_ingestion_service()

    try:
        result = service.ingest_memory_turns(request.turns)
    except MemoryIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return IngestSummary(
        type="memory",
        memories_added=result["memories_added"],
        dispatched=result["dispatched"],
    )
