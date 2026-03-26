"""Health check endpoint."""

from fastapi import APIRouter, Request, status
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = "healthy"


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint with database connectivity verification.

    Returns:
        HealthResponse with status "healthy" if database is reachable
    """
    # Verify database connectivity
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")

    return HealthResponse()
