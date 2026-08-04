from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from psx_data_hub.api import auth
from psx_data_hub.core.config import settings
from psx_data_hub.core.database import AsyncSessionLocal
from psx_data_hub.storage.repo import DataRepository

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


async def get_repo() -> DataRepository:
    async with AsyncSessionLocal() as session:
        yield DataRepository(session)


def _api_key_matches(candidate: str | None) -> bool:
    """Constant-time comparison of `candidate` against the configured key set.

    Prevents trivial timing side-channels on `key in [...]` (BUG-12).
    """
    if not candidate:
        return False
    match = False
    for known in settings.api_keys:
        # `compare_digest` returns False if lengths differ; the OR keeps us
        # from short-circuiting through the loop.
        match |= secrets.compare_digest(str(candidate), str(known))
    return match


def require_api_key(
    api_key: Annotated[str | None, Depends(api_key_header)],
    token: Annotated[str | None, Depends(oauth2_bearer)] = None,
):
    """Apply the same configured auth policy used by compatibility routes.

    The historical name is retained because all `/v1` routers import it, but
    `AUTH_MODE` is authoritative for the whole API. `API_KEY_REQUIRED` remains
    the backwards-compatible switch used when authentication mode is `off`.
    """
    return require_auth(api_key=api_key, token=token)


def require_auth(
    api_key: Annotated[str | None, Depends(api_key_header)] = None,
    token: Annotated[str | None, Depends(oauth2_bearer)] = None,
):
    if settings.auth_mode == "off":
        if settings.api_key_required and _api_key_matches(api_key):
            return {"type": "api-key", "principal": api_key}
        if settings.api_key_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key",
                headers={"WWW-Authenticate": "Api-Key"},
            )
        return {"type": "public"}

    if settings.auth_mode in {"api_key", "hybrid"}:
        if _api_key_matches(api_key):
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
