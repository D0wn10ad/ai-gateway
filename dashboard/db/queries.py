"""Database queries for usage data."""
from datetime import datetime, timedelta

import asyncpg


def get_billing_period_dates() -> tuple[datetime, datetime]:
    """
    Calculate current 7-day rolling window.

    Returns:
        (start_time, end_time) as timezone-naive datetimes (UTC)
        LiteLLM stores timestamps without timezone, so we use naive UTC
    """
    # Use UTC for database queries (LiteLLM stores naive UTC timestamps)
    now_utc = datetime.utcnow()
    start_time = now_utc - timedelta(days=7)
    return start_time, now_utc


async def get_user_spend(pool: asyncpg.Pool, user_email: str) -> dict:
    """
    Query LiteLLM_SpendLogs for user's weekly spend by model.

    Args:
        pool: asyncpg connection pool
        user_email: User's email from token (matches end_user column)

    Returns:
        Dict with period dates and model breakdown list
    """
    start_time, end_time = get_billing_period_dates()

    # Parameterized query prevents SQL injection
    # asyncpg uses server-side prepared statements
    query = """
        SELECT
            model,
            COALESCE(SUM(spend), 0) as spend,
            COALESCE(SUM(total_tokens), 0) as tokens
        FROM "LiteLLM_SpendLogs"
        WHERE end_user = $1
          AND "startTime" >= $2
          AND "startTime" < $3
        GROUP BY model
        ORDER BY spend DESC;
    """

    # Always use context manager to release connections
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_email, start_time, end_time)

    # Format dates for display (e.g., "Jan 17" and "Jan 24, 2025")
    return {
        "period_start": start_time.strftime("%b %d"),
        "period_end": end_time.strftime("%b %d, %Y"),
        "models": [dict(row) for row in rows],
    }


async def get_user_budget(pool: asyncpg.Pool, user_email: str) -> float | None:
    """
    Get user's budget limit from LiteLLM database.

    Looks up the user in LiteLLM_EndUserTable and joins to LiteLLM_BudgetTable
    to get their assigned max_budget.

    Args:
        pool: asyncpg connection pool
        user_email: User's email (matches user_id in LiteLLM_EndUserTable)

    Returns:
        max_budget if user has an assigned budget_id, None otherwise
        (caller should use DEFAULT_WEEKLY_BUDGET as fallback)
    """
    query = """
        SELECT b.max_budget
        FROM "LiteLLM_EndUserTable" e
        JOIN "LiteLLM_BudgetTable" b ON e.budget_id = b.budget_id
        WHERE e.user_id = $1
          AND b.max_budget IS NOT NULL;
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_email)

    if row and row["max_budget"] is not None:
        return float(row["max_budget"])
    return None
