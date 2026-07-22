import os

from fastapi import APIRouter

from app.services.embeddings import get_embedding_provider
from schema.response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    provider = get_embedding_provider()
    return HealthResponse(
        app=os.getenv("APP_NAME", "comori-rag-indexer"),
        embedding_provider=provider.name,
        embedding_dim=provider.dimension,
    )
