from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

from psx_data_hub.core.config import settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass(frozen=True)
class LegacyUser:
    username: str
    password_hash: str
    scopes: list[str]


def _parse_users() -> list[LegacyUser]:
    if not settings.legacy_users:
        return []

    parsed: list[LegacyUser] = []
    for user_entry in settings.legacy_users:
        if not isinstance(user_entry, str):
            continue
        if ":" not in user_entry:
            continue

        parts = [part.strip() for part in user_entry.split(":") if part.strip()]
        if len(parts) < 2:
            continue

        username = parts[0]
        password = parts[1]
        raw_scopes = parts[2] if len(parts) > 2 else ""
        scopes = [scope.strip() for scope in raw_scopes.split("|") if scope.strip()]
        if not scopes:
            scopes = ["public"]

        # If a plain password was provided, hash it once at boot-time.
        # Already hashed values (eg bcrypt) are accepted as-is.
        password_hash = password
        if not password.startswith("$2"):
            password_hash = pwd_context.hash(password)
        parsed.append(LegacyUser(username=username, password_hash=password_hash, scopes=scopes))
    return parsed


_USERS: list[LegacyUser] | None = None


def _load_users() -> list[LegacyUser]:
    global _USERS
    if _USERS is None:
        _USERS = _parse_users()
    return _USERS


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def authenticate_user(username: str, password: str) -> LegacyUser | None:
    for user in _load_users():
        if user.username != username:
            continue
        if not verify_password(password, user.password_hash):
            continue
        return user
    return None


def create_access_token(username: str, scopes: list[str], expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload = {
        "sub": username,
        "scope": " ".join(scopes),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _extract_scopes(scope: Any) -> list[str]:
    if not scope:
        return ["public"]
    if isinstance(scope, str):
        return [part for part in scope.split(" ") if part]
    if isinstance(scope, list):
        return [str(part) for part in scope if part]
    return ["public"]


def parse_token(token: str | None) -> tuple[str, list[str]]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        scope = payload.get("scope")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not username or not isinstance(username, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return str(username), _extract_scopes(scope)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> tuple[str, list[str]]:
    return parse_token(token)


def token_subject(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> tuple[str, list[str]]:
    user = authenticate_user(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user.username, user.scopes
