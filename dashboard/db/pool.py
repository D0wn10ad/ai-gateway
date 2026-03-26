"""asyncpg connection pool management."""

import asyncpg
from fastapi import FastAPI


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Create an asyncpg connection pool.

    Args:
        dsn: PostgreSQL connection string

    Returns:
        Configured asyncpg pool
    """
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        max_queries=50000,
        max_inactive_connection_lifetime=300.0,
    )
    return pool


def get_pool(app: FastAPI) -> asyncpg.Pool:
    """Retrieve the connection pool from app state.

    Args:
        app: FastAPI application instance

    Returns:
        The asyncpg pool stored in app.state
    """
    return app.state.pool
