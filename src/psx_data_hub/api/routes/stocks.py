from __future__ import annotations

import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from psx_data_hub.api.dependencies import get_repo, require_api_key
from psx_data_hub.core.config import settings
from psx_data_hub.schemas.models import (
    DelayMetadata,
    EODPoint,
    QuoteResponse,
    SymbolItem,
    TimeseriesPoint,
)
from psx_data_hub.storage.repo import DataRepository, is_stale

router = APIRouter()

SYMBOL_RE = re.compile(r"^[A-Z0-9._-]{1,20}$")
# Two upstream intervals from PSX. See providers/psx_dps_provider.py.
ALLOWED_INTERVALS = {"int", "eod"}


def _validate_symbol(raw: str) -> str:
    normalized = raw.strip().upper()
    if not SYMBOL_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbol must be 1-20 chars, letters/digits/._- only",
        )
    return normalized


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _make_delay(source: str, source_ts: datetime | None, fetched_at: datetime | None) -> DelayMetadata:
    now = datetime.now(timezone.utc)
    fetched = _ensure_utc(fetched_at) or now
    return DelayMetadata(
        delay_minutes=settings.delay_minutes,
        source=source,
        source_timestamp=_ensure_utc(source_ts),
        fetched_at=fetched,
        cache_age_seconds=int((now - fetched).total_seconds()),
        data_source_notice=settings.data_source_notice,
        is_stale=is_stale(settings.stale_threshold_seconds, fetched),
    )


@router.get(
    "",
    response_model=list[SymbolItem],
    dependencies=[Depends(require_api_key)],
    summary="List all symbols",
)
@router.get(
    "/symbols",
    response_model=list[SymbolItem],
    dependencies=[Depends(require_api_key)],
    summary="List all symbols (alias)",
    include_in_schema=False,
)
async def list_symbols(
    repo: DataRepository = Depends(get_repo),
    include_inactive: bool = False,
):
    rows = await repo.list_symbols(active_only=not include_inactive)
    return [SymbolItem(symbol=row.symbol, name=row.name) for row in rows]


@router.get(
    "/{symbol}",
    response_model=QuoteResponse,
    dependencies=[Depends(require_api_key)],
    summary="Latest quote for a symbol",
)
async def get_stock_quote(symbol: str, repo: DataRepository = Depends(get_repo)):
    symbol_norm = _validate_symbol(symbol)
    row = await repo.get_latest_quote(symbol_norm)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no cached quote for symbol '{symbol_norm}'",
        )
    return QuoteResponse(
        symbol=row.symbol,
        name=row.name,
        ltp=row.ltp,
        change=row.change,
        change_pct=row.change_pct,
        volume=row.volume,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        delay=_make_delay(row.source, row.source_timestamp, row.fetched_at),
    )


@router.get(
    "/{symbol}/description",
    dependencies=[Depends(require_api_key)],
    summary="Company description",
)
async def get_company_description(symbol: str, repo: DataRepository = Depends(get_repo)):
    symbol_norm = _validate_symbol(symbol)
    quote = await repo.get_latest_quote(symbol_norm)
    symbol_row = await repo.get_symbol(symbol_norm)
    if quote is None and symbol_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no data for symbol '{symbol_norm}'",
        )
    src_ts = _ensure_utc(quote.source_timestamp) if quote and quote.source_timestamp else None
    return {
        "symbol": symbol_norm,
        "name": (quote.name if quote else None)
        or (symbol_row.name if symbol_row else None)
        or symbol_norm,
        "sector": symbol_row.sector if symbol_row else None,
        "description": None,
        "source": quote.source if quote else None,
        "source_timestamp": src_ts.isoformat() if src_ts else None,
    }


@router.get(
    "/{symbol}/history",
    response_model=list[TimeseriesPoint],
    dependencies=[Depends(require_api_key)],
    summary="Intraday / EOD time series",
)
async def get_stock_history(
    symbol: str,
    interval: str = Query("int", min_length=1, max_length=8),
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
    repo: DataRepository = Depends(get_repo),
):
    symbol_norm = _validate_symbol(symbol)
    interval_norm = interval.strip().lower()
    if interval_norm not in ALLOWED_INTERVALS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"interval must be one of {sorted(ALLOWED_INTERVALS)}",
        )
    if from_ts and to_ts and from_ts > to_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' must be <= 'to'",
        )

    rows = await repo.get_quote_history(
        symbol_norm, interval=interval_norm, from_ts=from_ts, to_ts=to_ts, limit=limit
    )
    return [
        TimeseriesPoint(
            symbol=row.symbol,
            interval=row.interval,
            period_start=row.period_start,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    ]


@router.get(
    "/{symbol}/eod",
    response_model=list[EODPoint],
    dependencies=[Depends(require_api_key)],
    summary="End-of-day OHLCV",
)
async def get_eod(
    symbol: str,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
    repo: DataRepository = Depends(get_repo),
):
    symbol_norm = _validate_symbol(symbol)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' must be <= 'to'",
        )
    rows = await repo.get_eod(symbol_norm, from_date=from_date, to_date=to_date, limit=limit)
    return [
        EODPoint(
            symbol=row.symbol,
            date=row.date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    ]
