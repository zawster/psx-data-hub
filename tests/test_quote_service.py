from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from psx_data_hub.providers.base import EodSnapshot
from psx_data_hub.services.quote_service import MarketDataService


@pytest.mark.asyncio
async def test_refresh_eod_populates_history_and_eod_tables():
    source_timestamp = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    eod = EodSnapshot(
        symbol="PSO",
        date=date(2026, 8, 3),
        close=347.49,
        volume=4_337_341,
        source_timestamp=source_timestamp,
        source="dps.psx.com.pk",
    )

    class Provider:
        source = "dps.psx.com.pk"

        async def fetch_eod(self, symbol, from_date=None, to_date=None):
            return [eod]

    class Repository:
        history = []
        records = []

        async def upsert_history_points(self, points):
            self.history = list(points)
            return len(self.history)

        async def upsert_eod_records(self, points):
            self.records = list(points)
            return len(self.records)

    repo = Repository()
    added = await MarketDataService(Provider(), repo).refresh_eod("PSO")

    assert added == 1
    assert repo.records == [eod]
    assert len(repo.history) == 1
    assert repo.history[0].interval == "eod"
    assert repo.history[0].period_start == source_timestamp
