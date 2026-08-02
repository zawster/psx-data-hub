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
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = DataRepository(session)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "psx-data-hub-worker"},
        ) as client:
            provider = PsxDpsProvider(client)
            service = MarketDataService(provider, repo)

            try:
                await service.refresh_market()
            except Exception as exc:
                log.warning("market refresh failed err=%s", exc)

            symbols = [symbol for symbol in settings.market_watchlist if symbol]
            for offset in range(0, len(symbols), settings.poll_symbols_per_tick):
                chunk = symbols[offset : offset + settings.poll_symbols_per_tick]
                for symbol in chunk:
                    try:
                        await service.refresh_symbol(symbol)
                    except Exception as exc:
                        log.warning("symbol refresh failed symbol=%s err=%s", symbol, exc)
                    await asyncio.sleep(0.2)

            # clean stale quote rows every cycle
            removed = await service.prune_old_quotes()
            if removed:
                log.info("pruned quotes removed=%s", removed)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    log.info("psx-data-hub worker started; interval=%ss", settings.poll_interval_seconds)
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
