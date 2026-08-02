from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from psx_data_hub.core.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_delay_minutes": settings.delay_minutes,
        "data_source_notice": settings.data_source_notice,
    }


@router.get("/status")
async def status():
    return {
        "status": "ok",
        "provider": "dps.psx.com.pk",
        "data_delay_minutes": settings.delay_minutes,
        "data_source_notice": settings.data_source_notice,
    }
