from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.response import HealthResponse
from app.services.embeddings import get_embedding_provider

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    provider = get_embedding_provider()
    return HealthResponse(
        app=settings.APP_NAME,
        embedding_provider=provider.name,
        embedding_dim=provider.dimension,
        comori_api_mode=settings.COMORI_API_MODE,
    )
