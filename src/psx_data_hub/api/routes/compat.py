from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm

from psx_data_hub.api import auth
from psx_data_hub.api.dependencies import get_repo, require_auth
from psx_data_hub.core.config import settings
from psx_data_hub.schemas.models import DelayMetadata
from psx_data_hub.storage.repo import DataRepository
from psx_data_hub.storage.models import MarketSnapshot

router = APIRouter()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return None


def _to_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _delay_from_snapshot(snapshot: MarketSnapshot | None, is_stale: bool = False) -> DelayMetadata:
    now = datetime.now(timezone.utc)
    if snapshot is None:
        return DelayMetadata(
            delay_minutes=settings.delay_minutes,
            source="unknown",
            source_timestamp=None,
            fetched_at=now,
            cache_age_seconds=0,
            data_source_notice=settings.data_source_notice,
            is_stale=True,
        )

    fetched_at = snapshot.fetched_at.replace(tzinfo=timezone.utc)
    stale = is_stale if snapshot.source_timestamp is None else (now - fetched_at).total_seconds() > settings.stale_threshold_seconds
    return DelayMetadata(
        delay_minutes=settings.delay_minutes,
        source=snapshot.source,
        source_timestamp=snapshot.source_timestamp,
        fetched_at=fetched_at,
        cache_age_seconds=int((now - fetched_at).total_seconds()),
        data_source_notice=settings.data_source_notice,
        is_stale=stale,
    )


def _extract_payload_value(payload: dict, keys: list[str]) -> object | None:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    for _, value in payload.items():
        if isinstance(value, dict):
            nested = _extract_payload_value(value, keys)
            if nested is not None:
                return nested
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    nested = _extract_payload_value(item, keys)
                    if nested is not None:
                        return nested
    return None


def _market_indices(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    indices = payload.get("indices")
    if isinstance(indices, list):
        return [item for item in indices if isinstance(item, dict)]
    return []


@router.get("/")
async def welcome():
    return {"Message": "Welcome to Pakistan First Stock Api"}


@router.post("/token")
async def issue_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = auth.authenticate_user(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(user.username, user.scopes)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/token-check", dependencies=[Depends(auth.get_current_user)])
async def token_check():
    return {"message": "You are authenticated!"}


@router.get("/volume", dependencies=[Depends(require_auth)])
async def get_volume(repo: DataRepository = Depends(get_repo)):
    snapshot = await repo.get_latest_market_snapshot()
    payload = snapshot.payload if snapshot else {}
    raw_value = _extract_payload_value(payload, ["volume", "total_volume", "market_volume", "tradesVolume"])
    volume = _to_int(raw_value)
    return {"metric": "volume", "value": volume or 0, "unit": "shares", "delay": _delay_from_snapshot(snapshot)}


@router.get("/status", dependencies=[Depends(require_auth)])
async def get_market_status(repo: DataRepository = Depends(get_repo)):
    snapshot = await repo.get_latest_market_snapshot()
    payload = snapshot.payload if snapshot else {}
    status_value = _to_str(_extract_payload_value(payload, ["market_status", "status", "session_status"])) or "unknown"
    return {
        "status": status_value,
        "delay": _delay_from_snapshot(snapshot),
    }


@router.get("/tradesinstockmarket", dependencies=[Depends(require_auth)])
async def get_total_trades(repo: DataRepository = Depends(get_repo)):
    snapshot = await repo.get_latest_market_snapshot()
    payload = snapshot.payload if snapshot else {}
    raw = _extract_payload_value(payload, ["trades", "trades_done", "numberOfTrades", "total_trades"])
    trades = _to_int(raw) or 0
    return {"metric": "trades_in_stock_market", "value": trades, "delay": _delay_from_snapshot(snapshot)}


@router.get("/totalcompanies", dependencies=[Depends(require_auth)])
async def get_total_companies(repo: DataRepository = Depends(get_repo)):
    total = await repo.count_symbols(active_only=True)
    return {"metric": "total_companies", "value": total, "delay": _delay_from_snapshot(await repo.get_latest_market_snapshot())}


@router.get("/companiesinloss", dependencies=[Depends(require_auth)])
async def get_companies_in_loss(repo: DataRepository = Depends(get_repo)):
    symbols = await repo.list_symbols(active_only=True)
    total_loss = 0
    for symbol in symbols:
        quote = await repo.get_latest_quote(symbol.symbol)
        if not quote:
            continue
        if quote.change is not None and quote.change < 0:
            total_loss += 1
    return {"metric": "companies_in_loss", "value": total_loss, "delay": _delay_from_snapshot(await repo.get_latest_market_snapshot())}


@router.get("/companiesinprofit", dependencies=[Depends(require_auth)])
async def get_companies_in_profit(repo: DataRepository = Depends(get_repo)):
    symbols = await repo.list_symbols(active_only=True)
    total_profit = 0
    for symbol in symbols:
        quote = await repo.get_latest_quote(symbol.symbol)
        if not quote:
            continue
        if quote.change is not None and quote.change > 0:
            total_profit += 1
    return {"metric": "companies_in_profit", "value": total_profit, "delay": _delay_from_snapshot(await repo.get_latest_market_snapshot())}


@router.get("/sectors", dependencies=[Depends(require_auth)])
async def get_sectors(repo: DataRepository = Depends(get_repo)):
    rows = await repo.list_symbols(active_only=True)
    sectors: dict[str, int] = {}
    for row in rows:
        sector = row.sector or "Unknown"
        sectors[sector] = sectors.get(sector, 0) + 1
    return {
        "metric": "sectors",
        "count": len(sectors),
        "items": [{"sector": sector, "companies": total} for sector, total in sorted(sectors.items())],
        "delay": _delay_from_snapshot(await repo.get_latest_market_snapshot()),
    }


@router.get("/sectorgraph", dependencies=[Depends(require_auth)])
async def get_sector_graph(repo: DataRepository = Depends(get_repo)):
    symbols = await repo.list_symbols(active_only=True)
    market = await repo.get_latest_market_snapshot()
    delay = _delay_from_snapshot(market)
    sectors: dict[str, dict[str, list[float]]] = {}
    for row in symbols:
        quote = await repo.get_latest_quote(row.symbol)
        if not quote or quote.change_pct is None:
            continue
        sector = row.sector or "Unknown"
        bucket = sectors.setdefault(sector, {"points": []})
        bucket["points"].append(_to_float(quote.change_pct))

    graph = []
    for sector, item in sorted(sectors.items()):
        points = [point for point in item["points"] if point is not None]
        if not points:
            continue
        avg = sum(points) / len(points)
        graph.append(
            {
                "sector": sector,
                "companies": len(points),
                "avg_change_pct": round(avg, 4),
            }
        )
    return {"metric": "sectorgraph", "items": graph, "delay": delay}


@router.get("/allindices", dependencies=[Depends(require_auth)])
async def get_all_indices(repo: DataRepository = Depends(get_repo)):
    snapshot = await repo.get_latest_market_snapshot()
    indices = _market_indices(snapshot.payload if snapshot else {})
    return {"indices": indices, "delay": _delay_from_snapshot(snapshot)}


@router.get("/getindex", dependencies=[Depends(require_auth)])
async def get_index(
    symbol: str = Query(..., alias="symbol", min_length=1),
    repo: DataRepository = Depends(get_repo),
):
    target = symbol.strip().upper()
    snapshot = await repo.get_latest_market_snapshot()
    delay = _delay_from_snapshot(snapshot)
    for row in _market_indices(snapshot.payload if snapshot else {}):
        row_symbol = str(row.get("symbol") or row.get("name") or "").upper()
        if row_symbol == target:
            return {
                "symbol": target,
                "value": row.get("value"),
                "change": row.get("change"),
                "change_pct": row.get("changePct") if row.get("changePct") is not None else row.get("change_pct"),
                "delay": delay,
            }
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"index '{symbol}' not found")


@router.get("/{company}/getalldata", dependencies=[Depends(require_auth)])
@router.post("/{company}/getalldata", dependencies=[Depends(require_auth)])
async def get_company_all_data(company: str, repo: DataRepository = Depends(get_repo)):
    symbol = company.upper()
    quote = await repo.get_latest_quote(symbol)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no data for company '{symbol}'")
    return {
        "symbol": symbol,
        "name": quote.name,
        "ltp": quote.ltp,
        "change": quote.change,
        "change_pct": quote.change_pct,
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "close": quote.close,
        "volume": quote.volume,
        "source": quote.source,
        "fetched_at": quote.fetched_at.replace(tzinfo=timezone.utc).isoformat(),
        "raw": quote.raw_payload,
    }


@router.get("/{company}/description", dependencies=[Depends(require_auth)])
@router.post("/{company}/description", dependencies=[Depends(require_auth)])
async def get_company_description(company: str, repo: DataRepository = Depends(get_repo)):
    symbol = company.upper()
    quote = await repo.get_latest_quote(symbol)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no data for company '{symbol}'")
    return {
        "symbol": symbol,
        "name": quote.name,
        "sector": (quote.raw_payload or {}).get("sector") if isinstance(quote.raw_payload, dict) else None,
        "description": None,
        "source_timestamp": quote.source_timestamp.replace(tzinfo=timezone.utc).isoformat()
        if quote.source_timestamp
        else None,
    }


@router.get("/{company}/equitydata", dependencies=[Depends(require_auth)])
@router.post("/{company}/equitydata", dependencies=[Depends(require_auth)])
async def get_company_equity_data(company: str, repo: DataRepository = Depends(get_repo)):
    symbol = company.upper()
    quote = await repo.get_latest_quote(symbol)
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no data for company '{symbol}'")
    return {
        "symbol": symbol,
        "name": quote.name,
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "close": quote.close,
        "ltp": quote.ltp,
        "volume": quote.volume,
        "source": quote.source,
        "fetched_at": quote.fetched_at.replace(tzinfo=timezone.utc).isoformat(),
    }
