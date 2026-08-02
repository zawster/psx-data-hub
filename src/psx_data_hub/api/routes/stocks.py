from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from psx_data_hub.api.dependencies import get_repo, require_api_key
from psx_data_hub.core.config import settings
from psx_data_hub.schemas.models import DelayMetadata, EODPoint, QuoteResponse, SymbolItem, TimeseriesPoint
from psx_data_hub.storage.repo import DataRepository, is_stale

router = APIRouter()


def _make_delay(source: str, source_ts: datetime | None, fetched_at: datetime | None) -> DelayMetadata:
    now = datetime.now(timezone.utc)
    fetched = fetched_at.replace(tzinfo=timezone.utc) if fetched_at else now
    return DelayMetadata(
        delay_minutes=settings.delay_minutes,
        source=source,
        source_timestamp=source_ts,
        fetched_at=fetched,
        cache_age_seconds=int((now - fetched).total_seconds()),
        data_source_notice=settings.data_source_notice,
        is_stale=is_stale(settings.stale_threshold_seconds, fetched),
    )


@router.get("", response_model=list[SymbolItem], dependencies=[Depends(require_api_key)])
async def list_symbols(
    repo: DataRepository = Depends(get_repo),
    include_inactive: bool = False,
):
    rows = await repo.list_symbols(active_only=not include_inactive)
    return [SymbolItem(symbol=row.symbol, name=row.name) for row in rows]


@router.get("/symbols", response_model=list[SymbolItem], dependencies=[Depends(require_api_key)])
async def list_symbols_alias(
    repo: DataRepository = Depends(get_repo),
    include_inactive: bool = False,
):
    rows = await repo.list_symbols(active_only=not include_inactive)
    return [SymbolItem(symbol=row.symbol, name=row.name) for row in rows]


@router.get("/company/{symbol}", response_model=QuoteResponse, dependencies=[Depends(require_api_key)])
async def get_company_data(symbol: str, repo: DataRepository = Depends(get_repo)):
    row = await repo.get_latest_quote(symbol.upper())
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no cached quote for symbol '{symbol}'. refresh interval may be delayed",
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


@router.get("/{symbol}/description", dependencies=[Depends(require_api_key)])
async def get_company_description(symbol: str, repo: DataRepository = Depends(get_repo)):
    row = await repo.get_latest_quote(symbol.upper())
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no cached quote for symbol '{symbol}'. refresh interval may be delayed",
        )
    return {
        "symbol": row.symbol,
        "name": row.name,
        "sector": None,
        "ltp": row.ltp,
        "source": row.source,
    }


@router.get("/{symbol}/equity", dependencies=[Depends(require_api_key)])
async def get_company_equity(symbol: str, repo: DataRepository = Depends(get_repo)):
    row = await repo.get_latest_quote(symbol.upper())
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no cached quote for symbol '{symbol}'. refresh interval may be delayed",
        )
    return {
        "symbol": row.symbol,
        "name": row.name,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "volume": row.volume,
        "ltp": row.ltp,
    }


@router.get("/{symbol}", response_model=QuoteResponse, dependencies=[Depends(require_api_key)])
async def get_stock_quote(symbol: str, repo: DataRepository = Depends(get_repo)):
    row = await repo.get_latest_quote(symbol.upper())
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no cached quote for symbol '{symbol}'. refresh interval may be delayed",
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


@router.get("/{symbol}/history", response_model=list[TimeseriesPoint], dependencies=[Depends(require_api_key)])
async def get_stock_history(
    symbol: str,
    interval: str = Query("5m", min_length=1),
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    repo: DataRepository = Depends(get_repo),
    limit: int = Query(500, ge=1, le=5000),
):
    rows = await repo.get_quote_history(
        symbol.upper(),
        interval=interval,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
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


@router.get("/{symbol}/eod", response_model=list[EODPoint], dependencies=[Depends(require_api_key)])
async def get_eod(
    symbol: str,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    repo: DataRepository = Depends(get_repo),
    limit: int = Query(500, ge=1, le=5000),
):
    rows = await repo.get_eod(symbol.upper(), from_date=from_date, to_date=to_date, limit=limit)
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
