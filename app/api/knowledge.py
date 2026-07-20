"""
Knowledge-path API routes.

Hosts the unified ingestion endpoint (spec section 2) plus the two query-flow
endpoints that comori-va calls directly:
  - POST /api/v1/ingest         (Branch A: knowledge doc upload | Branch B: memory turns)
  - POST /api/v1/embed/query    (embed a user query for comori-api's similarity search)
  - POST /api/v1/decode         (format/clean raw hits returned by comori-api)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.requests import Request

from app.api.memory import handle_memory_ingest
from app.config import Settings, get_settings
from app.models.request import (
    DecodeRequest,
    EmbedQueryRequest,
    IngestType,
    KnowledgeIngestMetadata,
    MemoryIngestRequest,
)
from app.models.response import DecodeResponse, EmbedQueryResponse, IngestSummary
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.ingestion import IngestionService
from app.services.parser import UnsupportedFileTypeError
from app.services.search import decode_hits, embed_query

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


def get_ingestion_service(settings: Settings = Depends(get_settings)) -> IngestionService:
    return IngestionService(settings=settings)


@router.post("/ingest", response_model=IngestSummary)
async def ingest(
    request: Request,
    settings: Settings = Depends(get_settings),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> IngestSummary:
    """
    Unified ingestion endpoint.

    - multipart/form-data with `type=knowledge`, a `file`, and a JSON
      `metadata` field  -> Branch A (document ingestion)
    - application/json body with `type: "memory"` and `turns: [...]`
      -> Branch B (conversation memory ingestion)
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        return await _ingest_knowledge_branch(request, ingestion_service, settings)

    if "application/json" in content_type:
        body = await request.json()
        if body.get("type") != IngestType.MEMORY.value:
            raise HTTPException(
                status_code=400,
                detail="JSON ingest body must have type='memory'. "
                "Use multipart/form-data with type='knowledge' for document ingestion.",
            )
        memory_request = MemoryIngestRequest.model_validate(body)
        return handle_memory_ingest(memory_request, ingestion_service)

    raise HTTPException(
        status_code=415,
        detail="Unsupported content type. Use multipart/form-data (knowledge) "
        "or application/json (memory).",
    )


async def _ingest_knowledge_branch(
    request: Request, ingestion_service: IngestionService, settings: Settings
) -> IngestSummary:
    form = await request.form()

    ingest_type = form.get("type")
    if ingest_type != IngestType.KNOWLEDGE.value:
        raise HTTPException(
            status_code=400, detail="multipart ingest requires type='knowledge'."
        )

    upload: UploadFile | None = form.get("file")  # type: ignore[assignment]
    if upload is None:
        raise HTTPException(status_code=400, detail="Missing required 'file' form field.")

    metadata_raw = form.get("metadata")
    if not metadata_raw:
        raise HTTPException(status_code=400, detail="Missing required 'metadata' form field.")

    try:
        metadata_dict = json.loads(metadata_raw)  # type: ignore[arg-type]
        metadata = KnowledgeIngestMetadata.model_validate(metadata_dict)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc

    raw_bytes = await upload.read()

    try:
        result = ingestion_service.ingest_knowledge_document(
            filename=upload.filename or "unknown", raw_bytes=raw_bytes, metadata=metadata
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    return IngestSummary(
        type="knowledge",
        docs_processed=result["docs_processed"],
        chunks_added=result["chunks_added"],
        chunks_updated=result["chunks_updated"],
        chunks_skipped=result["chunks_skipped"],
        mode=settings.COMORI_API_MODE,
        dispatched=result["dispatched"],
    )


@router.post("/embed/query", response_model=EmbedQueryResponse)
def embed_query_endpoint(
    payload: EmbedQueryRequest,
    provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> EmbedQueryResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")

    vector = embed_query(provider, payload.query)
    return EmbedQueryResponse(embedding=vector, dim=provider.dimension, provider=provider.name)


@router.post("/decode", response_model=DecodeResponse)
def decode_endpoint(payload: DecodeRequest) -> DecodeResponse:
    return DecodeResponse(results=decode_hits(payload.hits))
