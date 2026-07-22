"""
Application entry point for comori-rag-indexer.

Mounts all API routers and configures the FastAPI application instance.
Run with:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api import health, knowledge, memory

app = FastAPI(
    title="comori-rag-indexer",
    description=(
        "Text extraction, chunking, embedding generation, and decoding service. "
        "Ingestion endpoint: POST /api/v1/ingest. "
        "Query flow endpoints: POST /api/v1/embed/query, POST /api/v1/decode."
    ),
    version="0.1.0",
)

# --- Routers ----------------------------------------------------------------
app.include_router(health.router)
app.include_router(knowledge.router)
app.include_router(memory.router)
