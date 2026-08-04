"""Live integration checks against the real dps.psx.com.pk endpoints.

Opt-in: set `PSX_LIVE=1` to enable. Skipped by default so CI stays offline.

The purpose is a smoke test that catches upstream schema drift — the exact
failure mode that produced BUG-0. If PSX changes their column headers or JSON
shape again, these tests will surface it before the rest of the app silently
degrades to empty responses.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest
import pytest_asyncio

from psx_data_hub.providers.base import ProviderTemporaryError

LIVE = os.environ.get("PSX_LIVE") == "1"


pytestmark = pytest.mark.skipif(not LIVE, reason="set PSX_LIVE=1 to run live checks")


async def _retry_temporary(callback, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return await callback()
        except ProviderTemporaryError:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": "psx-data-hub-tests/0.2.0"},
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_market_watch_returns_price_table(client):
    from psx_data_hub.providers.psx_dps_provider import PsxDpsProvider

    provider = PsxDpsProvider(client=client)
    payload, ts = await _retry_temporary(provider.fetch_market_overview)
    assert ts is not None
    tickers = payload.get("tickers") or []
    indices = payload.get("indices") or []
    assert len(tickers) > 100, f"expected many tickers, got {len(tickers)}"
    assert len(indices) > 5, f"expected live indices, got {len(indices)}"
    assert isinstance(payload.get("trades"), int)
    assert isinstance(payload.get("market_status"), str) and payload["market_status"]

    # A handful of PSX blue-chips must appear.
    symbols = {row["symbol"] for row in tickers}
    for expected in {"PSO", "OGDC", "FFC", "MEBL", "HUBC"}:
        assert expected in symbols, f"{expected} missing from market-watch"

    # Every row has a numeric current price.
    for row in tickers[:20]:
        assert isinstance(row.get("current"), (int, float))


@pytest.mark.asyncio
async def test_indices_endpoint_returns_named_indices(client):
    from psx_data_hub.providers.psx_dps_provider import PsxDpsProvider

    provider = PsxDpsProvider(client=client)
    payload, _ = await _retry_temporary(provider.fetch_market_overview)
    indices = payload.get("indices") or []
    assert len(indices) > 0, "expected at least one index row from /indices"
    names = {row["symbol"] for row in indices}
    assert "KSE100" in names, f"KSE100 missing from indices: {names}"
    for row in indices[:5]:
        assert isinstance(row.get("value"), (int, float))


@pytest.mark.asyncio
async def test_intraday_timeseries_returns_json(client):
    from psx_data_hub.providers.psx_dps_provider import PsxDpsProvider

    provider = PsxDpsProvider(client=client)
    points = await _retry_temporary(
        lambda: provider.fetch_timeseries("PSO", interval="int")
    )
    assert isinstance(points, list)
    # We can't guarantee non-empty (market may be closed), but the call must
    # not raise and each point must be well-formed.
    for p in points[:5]:
        assert p.symbol == "PSO"
        assert p.close is not None
