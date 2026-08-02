from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel
from pydantic import Field


class DelayMetadata(BaseModel):
    delay_minutes: int
    source: str
    source_timestamp: Optional[datetime] = None
    fetched_at: datetime
    cache_age_seconds: int
    data_source_notice: str
    is_stale: bool = False


class QuoteResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    ltp: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    delay: DelayMetadata


class MarketIndexPoint(BaseModel):
    symbol: str
    value: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None


class MarketSummaryResponse(BaseModel):
    fetched_at: datetime
    source_timestamp: Optional[datetime] = None
    delay: DelayMetadata
    payload: dict[str, Any] = Field(default_factory=dict)
    indices: list[MarketIndexPoint] = Field(default_factory=list)


class SymbolItem(BaseModel):
    symbol: str
    name: Optional[str] = None


class TimeseriesPoint(BaseModel):
    symbol: str
    interval: str
    period_start: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None


class EODPoint(BaseModel):
    symbol: str
    date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
