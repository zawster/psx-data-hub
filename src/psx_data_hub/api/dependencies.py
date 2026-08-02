from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from fastapi.security import OAuth2PasswordBearer

from psx_data_hub.core.config import settings
from psx_data_hub.core.database import AsyncSessionLocal
from psx_data_hub.api import auth
from psx_data_hub.storage.repo import DataRepository

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


async def get_repo() -> DataRepository:
    async with AsyncSessionLocal() as session:
        yield DataRepository(session)


def require_api_key(api_key: Annotated[str | None, Depends(api_key_header)]):
    if not settings.api_key_required:
        return "public"
    if not api_key or api_key not in settings.api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
    return api_key


def require_auth(
    api_key: Annotated[str | None, Depends(api_key_header)] = None,
    token: Annotated[str | None, Depends(oauth2_bearer)] = None,
):
    if settings.auth_mode == "off":
        if settings.api_key_required and api_key is not None and api_key in settings.api_keys:
            return {"type": "api-key", "principal": api_key}
        if settings.api_key_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key",
                headers={"WWW-Authenticate": "Api-Key"},
            )
        return {"type": "public"}

    if settings.auth_mode in {"api_key", "hybrid"}:
        if api_key is not None and api_key in settings.api_keys:
            return {"type": "api-key", "principal": api_key}

    if settings.auth_mode in {"jwt", "hybrid"}:
        if token:
            username, scopes = auth.parse_token(token)
            return {"type": "jwt", "principal": username, "scopes": scopes}

    if settings.auth_mode == "api_key":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "Api-Key"},
        )
    if settings.auth_mode == "jwt":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Api-Key, Bearer"},
    )


async def require_jwt_user(principal=Depends(require_auth)):
    if principal.get("type") != "jwt":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="JWT token required for this endpoint",
        )
    return principal
