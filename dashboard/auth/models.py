"""Pydantic models for authentication and user context."""

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """Authenticated user context passed to endpoints."""
    email: str
    user_id: str
    name: str | None = None
