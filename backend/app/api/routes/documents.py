from fastapi import APIRouter

from backend.app.core.config import get_settings
from backend.app.schemas.document import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns 200 with a simple status body. Used by Render's health check.",
)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app_env=settings.app_env)
