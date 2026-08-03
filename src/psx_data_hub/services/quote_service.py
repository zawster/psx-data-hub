from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from psx_data_hub.providers.base import (
    EodSnapshot,
    ProviderParseError,
    ProviderPermanentError,
    ProviderTemporaryError,
    QuoteSnapshot,
    StockMarketDataProvider,
    TimeseriesPoint,
)
from psx_data_hub.providers.psx_dps_provider import PsxDpsProvider
from psx_data_hub.storage.repo import DataRepository

log = logging.getLogger("psx_data_hub.service")


class MarketDataService:
    """Orchestrates polling, normalization and persistence."""

    def __init__(self, provider: StockMarketDataProvider, repo: DataRepository):
        self.provider = provider
        self.repo = repo

    async def _with_retries(self, callback, symbol: str, max_attempts: int = 3):
        delay = 0.25
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return await callback()
            except ProviderPermanentError:
                # No point in retrying a 404 or unknown-symbol response.
                raise
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

    async def refresh_market(self) -> dict[str, Any]:
        payload, source_ts = await self._with_retries(
            lambda: self.provider.fetch_market_overview(),
            symbol="__market__",
            max_attempts=3,
        )
        await self.repo.upsert_market_snapshot(payload, source_ts, source=self.provider.source)
        # Persist ticker rows as quotes + symbols in one pass — this is the
        # bulk-refresh path that replaces per-symbol scraping.
        tickers = payload.get("tickers") or []
        if tickers and isinstance(self.provider, PsxDpsProvider):
            await self._bulk_upsert_from_market_watch(tickers)
        return payload

    async def _bulk_upsert_from_market_watch(self, tickers: list[dict[str, Any]]) -> None:
        for row in tickers:
            try:
                await self.repo.upsert_symbol(
                    row["symbol"], name=None, sector=row.get("sector")
                )
                await self.repo.upsert_quote(
                    QuoteSnapshot(
                        symbol=row["symbol"],
                        source=self.provider.source,
                        name=None,
                        ltp=row.get("current"),
                        change=row.get("change"),
                        change_pct=row.get("change_pct"),
                        volume=(
                            int(row["volume"])
                            if isinstance(row.get("volume"), (int, float))
                            else None
                        ),
                        open=row.get("open"),
                        high=row.get("high"),
                        low=row.get("low"),
                        close=row.get("ldcp"),
                        source_timestamp=datetime.now(timezone.utc),
                        raw=row,
                    )
                )
            except Exception as exc:  # never let one bad row kill the whole tick
                log.warning("bulk upsert failed symbol=%s err=%s", row.get("symbol"), exc)

    async def refresh_symbol(self, symbol: str) -> None:
        quote: QuoteSnapshot = await self._with_retries(
            lambda: self.provider.fetch_quote(symbol),
            symbol=symbol,
            max_attempts=3,
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
        interval: str = "int",
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> int:
        points: list[TimeseriesPoint] = []
        for point in await self.provider.fetch_timeseries(symbol, interval):
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
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        return await self.repo.delete_old_quotes(cutoff)
