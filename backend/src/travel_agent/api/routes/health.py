from fastapi import APIRouter

from travel_agent.api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness check. Returns 200 when the server is up."""
    return HealthResponse()
