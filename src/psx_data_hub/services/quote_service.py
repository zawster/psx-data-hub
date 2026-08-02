from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Iterable

from psx_data_hub.providers.base import (
    EodSnapshot,
    ProviderParseError,
    ProviderTemporaryError,
    QuoteSnapshot,
    StockMarketDataProvider,
    TimeseriesPoint,
)
from psx_data_hub.storage.repo import DataRepository


class MarketDataService:
    """Orchestrates polling, normalization and persistence."""

    def __init__(self, provider: StockMarketDataProvider, repo: DataRepository):
        self.provider = provider
        self.repo = repo

    async def _with_retries(self, callback, symbol: str, max_attempts: int = 3):
        delay = 0.25
        last_error = None
        for attempt in range(max_attempts):
            try:
                return await callback()
            except (ProviderTemporaryError, ProviderParseError) as exc:
                last_error = exc
                if attempt == max_attempts - 1:
                    raise
            except Exception:
                raise
            await asyncio.sleep(delay + random.uniform(0, delay))
            delay *= 2
        if last_error:
            raise last_error

    async def refresh_market(self) -> None:
        payload, source_ts = await self._with_retries(
            lambda: self.provider.fetch_market_overview(), symbol="__market__", max_attempts=3
        )
        await self.repo.upsert_market_snapshot(payload, source_ts, source=self.provider.source)

    async def refresh_symbol(self, symbol: str) -> None:
        quote: QuoteSnapshot = await self._with_retries(
            lambda: self.provider.fetch_quote(symbol), symbol=symbol, max_attempts=3
        )
        await self.repo.upsert_symbol(symbol.upper(), quote.name)
        await self.repo.upsert_quote(quote)

    async def refresh_symbols(self, symbols: Iterable[str]) -> int:
        count = 0
        for symbol in symbols:
            try:
                await self.refresh_symbol(symbol)
                count += 1
            except Exception:
                continue
            await asyncio.sleep(0.05)
        return count

    async def refresh_timeseries(
        self,
        symbol: str,
        interval: str = "5m",
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> int:
        points: list[TimeseriesPoint] = []
        rows = await self.provider.fetch_timeseries(symbol, interval)
        for point in rows:
            if from_ts is not None and point.period_start < from_ts:
                continue
            if to_ts is not None and point.period_start > to_ts:
                continue
            points.append(point)
        return await self.repo.upsert_history_points(points)

    async def refresh_eod(
        self,
        symbol: str,
        from_date=None,
        to_date=None,
    ) -> int:
        points: list[EodSnapshot] = []
        for point in await self.provider.fetch_eod(symbol, from_date=from_date, to_date=to_date):
            points.append(point)
        return await self.repo.upsert_eod_records(points)

    async def prune_old_quotes(self) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=2)
        return await self.repo.delete_old_quotes(cutoff)
