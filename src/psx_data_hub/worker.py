from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from psx_data_hub.core.config import settings
from psx_data_hub.core.database import AsyncSessionLocal, init_db
from psx_data_hub.providers.psx_dps_provider import PsxDpsProvider
from psx_data_hub.services.quote_service import MarketDataService
from psx_data_hub.storage.repo import DataRepository

log = logging.getLogger("psx_data_hub.worker")


async def poll_once() -> None:
    """Single poll cycle.

    Strategy:
      1. Pull `/market-watch` once — this returns every quote for every listed
         symbol in one request. Persist as a market snapshot AND as per-symbol
         quotes (via `refresh_market` → `_bulk_upsert_from_market_watch`).
      2. Optionally refresh timeseries for the configured watchlist. This is
         still per-symbol and can be disabled by setting an empty watchlist.
      3. Prune expired quote rows.
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = DataRepository(session)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "psx-data-hub-worker/0.2.0"},
        ) as client:
            provider = PsxDpsProvider(client)
            service = MarketDataService(provider, repo)

            try:
                payload = await service.refresh_market()
                log.info(
                    "market refreshed tickers=%s indices=%s",
                    len(payload.get("tickers") or []),
                    len(payload.get("indices") or []),
                )
            except Exception as exc:
                log.warning("market refresh failed err=%s", exc)

            # Per-symbol timeseries + EOD refresh for the watchlist (opt-in).
            # `int` gives intraday points; `eod` populates `/v1/stocks/{sym}/eod`.
            symbols = [s for s in settings.market_watchlist if s]
            for offset in range(0, len(symbols), settings.poll_symbols_per_tick):
                chunk = symbols[offset : offset + settings.poll_symbols_per_tick]
                for symbol in chunk:
                    for interval in ("int", "eod"):
                        try:
                            # Populates `history_points` for
                            # /v1/stocks/{sym}/history?interval={int,eod}.
                            await service.refresh_timeseries(symbol, interval=interval)
                        except Exception as exc:
                            log.warning(
                                "history refresh failed symbol=%s interval=%s err=%s",
                                symbol, interval, exc,
                            )
                    try:
                        # Populates `eod_records` for /v1/stocks/{sym}/eod.
                        await service.refresh_eod(symbol)
                    except Exception as exc:
                        log.warning(
                            "eod refresh failed symbol=%s err=%s", symbol, exc
                        )
                    try:
                        await service.refresh_eod(symbol)
                    except Exception as exc:
                        log.warning("eod refresh failed symbol=%s err=%s", symbol, exc)
                    await asyncio.sleep(0.2)

            removed = await service.prune_old_quotes()
            if removed:
                log.info("pruned quotes removed=%s", removed)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    log.info(
        "psx-data-hub worker started; interval=%ss", settings.poll_interval_seconds
    )
    while True:
        start = datetime.now(timezone.utc)
        try:
            await poll_once()
        except Exception as exc:
            log.exception("poll run failed: %s", exc)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        sleep_for = max(0.0, settings.poll_interval_seconds - elapsed)
        await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    asyncio.run(main())
