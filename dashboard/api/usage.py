"""Usage data API endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from auth.token_validator import get_current_user
from auth.models import CurrentUser
from config import settings
from db.queries import get_user_spend, get_user_budget
from models.responses import UsageResponse, ModelSpend

router = APIRouter(prefix="/api", tags=["usage"])


@router.get(
    "/usage",
    response_model=UsageResponse,
    responses={
        401: {"description": "Invalid or expired token"},
        503: {"description": "Database unavailable"},
    },
)
async def get_usage(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UsageResponse:
    """
    Get authenticated user's weekly spend and model breakdown.

    Requires valid Open WebUI Bearer token in Authorization header.
    Returns spend data for the current 7-day rolling window.
    """
    pool = request.app.state.pool

    try:
        # Fetch spend data and user's budget limit in parallel
        data = await get_user_spend(pool, current_user.email)
        user_budget = await get_user_budget(pool, current_user.email)
    except Exception as e:
        # Log error but don't expose details
        print(f"Database error for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        )

    # Use user's assigned budget or fall back to global default
    budget_limit = user_budget if user_budget is not None else settings.DEFAULT_WEEKLY_BUDGET

    # Calculate totals
    total_spend = sum(m["spend"] for m in data["models"])
    percentage_used = round((total_spend / budget_limit) * 100, 2)

    # Build model list with percentages
    models = [
        ModelSpend(
            model=m["model"],
            spend=round(m["spend"], 4),
            tokens=int(m["tokens"]),
            percentage=round((m["spend"] / budget_limit) * 100, 2),
        )
        for m in data["models"]
    ]

    return UsageResponse(
        period_start=data["period_start"],
        period_end=data["period_end"],
        total_spend=round(total_spend, 4),
        percentage_used=percentage_used,
        models=models,
    )
