from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text

from psx_data_hub.api.dependencies import get_repo
from psx_data_hub.core.config import settings
from psx_data_hub.storage.repo import DataRepository

router = APIRouter()


def _provider_host() -> str:
    base = settings.provider_base_url or ""
    return base.replace("https://", "").replace("http://", "").rstrip("/") or "unknown"


@router.get("/health")
async def health(repo: DataRepository = Depends(get_repo)):
    """Liveness + shallow readiness probe.

    Touches the DB with `SELECT 1` and reports the age of the latest market
    snapshot so ops can catch a stalled worker without checking downstream
    endpoints.
    """
    db_ok = True
    try:
        await repo._session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    latest = await repo.get_latest_market_snapshot() if db_ok else None
    now = datetime.now(timezone.utc)
    last_fetch_age = None
    if latest is not None:
        fa = latest.fetched_at
        if fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        last_fetch_age = int((now - fa).total_seconds())

    return {
        "status": "ok" if db_ok else "degraded",
        "timestamp": now.isoformat(),
        "database": "ok" if db_ok else "unreachable",
        "provider": _provider_host(),
        "data_delay_minutes": settings.delay_minutes,
        "data_source_notice": settings.data_source_notice,
        "last_market_fetch_age_seconds": last_fetch_age,
    }


@router.get("/status")
async def status():
    return {
        "status": "ok",
        "provider": _provider_host(),
        "data_delay_minutes": settings.delay_minutes,
        "data_source_notice": settings.data_source_notice,
    }
