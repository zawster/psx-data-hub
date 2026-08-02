from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Optional


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    source: str
    name: Optional[str] = None
    ltp: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    source_timestamp: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TimeseriesPoint:
    symbol: str
    interval: str
    period_start: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    source_timestamp: Optional[datetime] = None
    source: str = "psx"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EodSnapshot:
    symbol: str
    date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    source_timestamp: Optional[datetime] = None
    source: str = "psx"
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Base provider error."""


class ProviderParseError(ProviderError):
    """Response could not be parsed into known model fields."""


class ProviderTemporaryError(ProviderError):
    """Retryable provider failure."""


class ProviderPermanentError(ProviderError):
    """Non-retryable provider failure."""


class StockMarketDataProvider(ABC):
    source: str

    @abstractmethod
    async def fetch_market_overview(self) -> tuple[dict[str, Any], datetime | None]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def fetch_timeseries(self, symbol: str, interval: str) -> list[TimeseriesPoint]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_eod(self, symbol: str, from_date: date | None = None, to_date: date | None = None) -> list[EodSnapshot]:
        raise NotImplementedError
