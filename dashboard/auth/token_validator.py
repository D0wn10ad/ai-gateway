"""Open WebUI token validation dependency for FastAPI."""
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.models import CurrentUser

security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> CurrentUser:
    """
    Validate token by calling Open WebUI's /api/v1/auths/ endpoint.

    Uses the shared httpx client stored on app.state during lifespan.
    Raises HTTPException 401 if token is invalid/expired.
    """
    token = credentials.credentials
    http_client: httpx.AsyncClient = request.app.state.http_client

    try:
        response = await http_client.get(
            "/api/v1/auths/",
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.RequestError as e:
        print(f"Open WebUI connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_data = response.json()

    email = (user_data.get("email") or "").lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User has no email",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        email=email,
        user_id=user_data.get("id", ""),
        name=user_data.get("name"),
    )
