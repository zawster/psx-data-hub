from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from psx_data_hub.api.dependencies import get_repo, require_api_key
from psx_data_hub.core.config import settings
from psx_data_hub.schemas.models import (
    DelayMetadata,
    MarketIndexPoint,
    MarketSummaryResponse,
)
from psx_data_hub.storage.repo import DataRepository, is_stale
from psx_data_hub.storage.models import MarketSnapshot

router = APIRouter()


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _make_delay(snapshot: MarketSnapshot) -> DelayMetadata:
    now = datetime.now(timezone.utc)
    fetched = _ensure_utc(snapshot.fetched_at) or now
    return DelayMetadata(
        delay_minutes=settings.delay_minutes,
        source=snapshot.source,
        source_timestamp=_ensure_utc(snapshot.source_timestamp),
        fetched_at=fetched,
        cache_age_seconds=int((now - fetched).total_seconds()),
        data_source_notice=settings.data_source_notice,
        is_stale=is_stale(settings.stale_threshold_seconds, fetched),
    )


@router.get(
    "/market",
    response_model=MarketSummaryResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_market(repo: DataRepository = Depends(get_repo)):
    snapshot = await repo.get_latest_market_snapshot()
    if snapshot is None:
        now = datetime.now(timezone.utc)
        return MarketSummaryResponse(
            fetched_at=now,
            source_timestamp=None,
            delay=DelayMetadata(
                delay_minutes=settings.delay_minutes,
                source="unknown",
                source_timestamp=None,
                fetched_at=now,
                cache_age_seconds=0,
                data_source_notice=settings.data_source_notice,
                is_stale=True,
            ),
            payload={"status": "no_data"},
            indices=[],
        )

    payload = snapshot.payload or {}
    indices: list[MarketIndexPoint] = []
    for row in payload.get("indices", []) if isinstance(payload, dict) else []:
        if isinstance(row, dict):
            indices.append(
                MarketIndexPoint(
                    symbol=str(row.get("symbol") or row.get("name") or "").upper(),
                    value=row.get("value"),
                    change=row.get("change"),
                    change_pct=row.get("changePct")
                    if row.get("changePct") is not None
                    else row.get("change_pct"),
                )
            )

    return MarketSummaryResponse(
        fetched_at=_ensure_utc(snapshot.fetched_at),
        source_timestamp=_ensure_utc(snapshot.source_timestamp),
        delay=_make_delay(snapshot),
        payload=payload,
        indices=indices,
    )
