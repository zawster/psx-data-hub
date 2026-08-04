from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from psx_data_hub.providers.base import TimeseriesPoint
from psx_data_hub.storage.models import Base
from psx_data_hub.storage.repo import DataRepository


@pytest.mark.asyncio
async def test_sqlite_history_upsert_batches_large_payloads():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    start = datetime(2026, 8, 3, tzinfo=timezone.utc)
    points = [
        TimeseriesPoint(
            symbol="PSO",
            interval="int",
            period_start=start + timedelta(seconds=offset),
            close=350.0 + offset / 100,
            volume=offset,
            source_timestamp=start + timedelta(seconds=offset),
            source="test",
        )
        for offset in range(200)
    ]

    async with session_factory() as session:
        repo = DataRepository(session)
        assert await repo.upsert_history_points(points) == 200
        assert await repo.upsert_history_points(points) == 0

    await engine.dispose()
