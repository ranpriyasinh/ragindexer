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
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.requests import Request

from app.api.memory import handle_memory_ingest
from app.config import Settings, get_settings
from app.models.request import (
    DecodeHit,
    DecodeRequest,
    EmbedQueryRequest,
    IngestType,
    KnowledgeIngestMetadata,
    MemoryIngestRequest,
    RetrieveRequest,
)

from app.models.response import DecodeResponse, EmbedQueryResponse, IngestSummary
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.ingestion import IngestionService
from app.services.parser import UnsupportedFileTypeError
from app.services.search import decode_hits, embed_query

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

DEFAULT_METADATA_EXAMPLE = json.dumps(
    {
        "source": "Nish CV 2026",
        "domain": "general",
        "evidence_tier": "tier3",
        "topic_tags": ["resume", "cv"],
    }
)


def get_ingestion_service(settings: Settings = Depends(get_settings)) -> IngestionService:
    return IngestionService(settings=settings)


@router.post(
    "/ingest",
    response_model=IngestSummary,
    summary="Unified Ingestion Endpoint",
    description=(
        "Unified ingestion endpoint supporting two modes:\n"
        "1. **Branch A (Knowledge Documents)**: Send `multipart/form-data` with `type='knowledge'`, "
        "a `file` (.pdf or .md), and a JSON string in `metadata`.\n"
        "2. **Branch B (Memory Turns)**: Send `application/json` with `type='memory'` and `turns=[...]`."
    ),
)
async def ingest(
    request: Request,
    type: Optional[str] = Form(
        "knowledge",
        description="Must be exactly 'knowledge' for file uploads.",
    ),
    file: Optional[UploadFile] = File(
        None, description="PDF or Markdown document file to upload (Branch A)"
    ),
    metadata: Optional[str] = Form(
        DEFAULT_METADATA_EXAMPLE,
        description="JSON metadata string for Branch A document metadata.",
    ),
    settings: Settings = Depends(get_settings),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> IngestSummary:
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        return await _ingest_knowledge_branch(type, file, metadata, ingestion_service, settings)

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
    ingest_type: Optional[str],
    upload: Optional[UploadFile],
    metadata_raw: Optional[str],
    ingestion_service: IngestionService,
    settings: Settings,
) -> IngestSummary:
    if ingest_type != IngestType.KNOWLEDGE.value:
        raise HTTPException(
            status_code=400, detail="multipart ingest requires type='knowledge'."
        )

    if upload is None:
        raise HTTPException(status_code=400, detail="Missing required 'file' form field.")

    if not metadata_raw:
        raise HTTPException(status_code=400, detail="Missing required 'metadata' form field.")

    try:
        metadata_dict = json.loads(metadata_raw)
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


from app.models.request import RetrieveRequest
from app.models.response import RetrieveResponse
from app.clients.nest_client import NestClient, NestClientError


def get_nest_client(settings: Settings = Depends(get_settings)) -> NestClient:
    return NestClient(settings=settings)


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(
    payload: RetrieveRequest,
    provider: EmbeddingProvider = Depends(get_embedding_provider),
    nest_client: NestClient = Depends(get_nest_client),
) -> RetrieveResponse:
    if payload.type != IngestType.KNOWLEDGE:
        raise HTTPException(status_code=501, detail="Only type='knowledge' retrieval is implemented.")

    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")

    vector = embed_query(provider, payload.query)

    try:
        raw_hits = nest_client.search_knowledge_chunks(vector, payload.k)
    except NestClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    hits = [DecodeHit.model_validate(h) for h in raw_hits]
    results = decode_hits(hits)

    print("\n=== KNOWLEDGE RETRIEVAL HITS ===")
    for r in results:
        print(f"Source: {r.source} | Score: {r.score:.4f}")
        print(f"Content: {r.text}\n")
    print("================================\n")

    return RetrieveResponse(type=payload.type.value, query=payload.query, k=payload.k, results=results)