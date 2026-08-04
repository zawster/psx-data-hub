from __future__ import annotations

import importlib
import sys
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest
from psx_data_hub.providers.base import EodSnapshot, QuoteSnapshot, TimeseriesPoint


def _clear_psx_modules() -> None:
    for module_name in list(sys.modules):
        if module_name.startswith("psx_data_hub"):
            del sys.modules[module_name]


def _seed_database() -> None:
    import asyncio

    from sqlalchemy import delete

    from psx_data_hub.core.database import AsyncSessionLocal, init_db
    from psx_data_hub.storage import models
    from psx_data_hub.storage.repo import DataRepository

    now = datetime.now(timezone.utc)

    async def _seed() -> None:
        await init_db()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(models.MarketSnapshot))
            await session.execute(delete(models.StockQuote))
            await session.execute(delete(models.HistoryPoint))
            await session.execute(delete(models.EodRecord))
            await session.execute(delete(models.Symbol))
            await session.commit()

            repo = DataRepository(session)
            await repo.upsert_symbol("PSO", "Pakistan State Oil Company Limited", "Energy")
            await repo.upsert_symbol("OGDC", "Oil & Gas Development Company Limited", "Energy")
            await repo.upsert_symbol("HBL", "Habib Bank Limited", "Financials")
            await session.commit()

            market_snapshot_payload = {
                "indices": [
                    {"symbol": "KSE100", "name": "KSE-100", "value": 65000.0, "change": 120.4, "changePct": 0.185},
                    {"symbol": "KSE200", "name": "KSE-200", "value": 42000.0, "change": -12.0, "changePct": -0.029},
                ],
                "total_volume": 12500000,
                "trades": 9876,
                "trades_done": 9876,
                "market_status": "open",
            }
            await repo.upsert_market_snapshot(
                payload=market_snapshot_payload,
                source_timestamp=now - timedelta(minutes=7),
                source="seed",
            )

            await repo.upsert_quote(
                QuoteSnapshot(
                    symbol="PSO",
                    source="seed",
                    name="Pakistan State Oil Company Limited",
                    ltp=325.25,
                    change=5.75,
                    change_pct=1.81,
                    volume=41000,
                    open=321.0,
                    high=330.5,
                    low=319.2,
                    close=325.0,
                    source_timestamp=now - timedelta(minutes=6),
                    raw={"sector": "Construction", "description": "PSO seed description"},
                )
            )
            await repo.upsert_quote(
                QuoteSnapshot(
                    symbol="OGDC",
                    source="seed",
                    name="Oil & Gas Development Company Limited",
                    ltp=88.3,
                    change=-1.8,
                    change_pct=-2.0,
                    volume=30000,
                    open=89.0,
                    high=89.9,
                    low=87.4,
                    close=88.1,
                    source_timestamp=now - timedelta(minutes=6),
                    raw={"sector": "Energy", "description": "OGDC seed description"},
                )
            )
            await repo.upsert_quote(
                QuoteSnapshot(
                    symbol="HBL",
                    source="seed",
                    name="Habib Bank Limited",
                    ltp=190.0,
                    change=0.0,
                    change_pct=0.0,
                    volume=18000,
                    open=190.0,
                    high=191.2,
                    low=188.9,
                    close=189.8,
                    source_timestamp=now - timedelta(minutes=6),
                    raw={"sector": "Financials", "description": "HBL seed description"},
                )
            )

            await repo.upsert_history_points(
                [
                    TimeseriesPoint(
                        symbol="PSO",
                        interval="eod",
                        period_start=now - timedelta(minutes=15),
                        open=323.0,
                        high=326.0,
                        low=322.8,
                        close=324.5,
                        volume=10200,
                        source_timestamp=now - timedelta(minutes=15),
                        source="seed",
                    ),
                    TimeseriesPoint(
                        symbol="PSO",
                        interval="eod",
                        period_start=now - timedelta(minutes=10),
                        open=324.5,
                        high=328.0,
                        low=324.2,
                        close=327.2,
                        volume=9800,
                        source_timestamp=now - timedelta(minutes=10),
                        source="seed",
                    ),
                ]
            )

            await repo.upsert_eod_records(
                [
                    EodSnapshot(
                        symbol="PSO",
                        date=date.today(),
                        open=320.0,
                        high=330.0,
                        low=319.0,
                        close=325.0,
                        volume=250000,
                        source="seed",
                        source_timestamp=now - timedelta(hours=1),
                    )
                ]
            )

    asyncio.run(_seed())



@pytest.fixture
def seeded_client_factory(tmp_path, monkeypatch):
    @contextmanager
    def _build(
        auth_mode: str = "off",
        api_key_required: bool = False,
        api_keys: list[str] | None = None,
        legacy_users: str = "demo:demo:public",
    ):
        api_keys = api_keys or []
        database_file = tmp_path / f"psx-{uuid.uuid4().hex}.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_file}")
        monkeypatch.setenv("AUTH_MODE", auth_mode)
        monkeypatch.setenv("API_KEY_REQUIRED", "true" if api_key_required else "false")
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5000")
        monkeypatch.setenv("RATE_LIMIT_BURST", "5000")
        monkeypatch.setenv("API_KEYS", ",".join(api_keys))
        monkeypatch.setenv("LEGACY_USERS", legacy_users)

        _clear_psx_modules()

        # Import path must occur after env vars are in place.
        importlib.import_module("psx_data_hub.core.config")

        _seed_database()

        from fastapi.testclient import TestClient
        from psx_data_hub.api.app import app

        with TestClient(app) as client:
            yield client

    return _build
