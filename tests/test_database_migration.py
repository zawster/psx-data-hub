from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from psx_data_hub.core.database import _migrate_sqlite_schema


@pytest.mark.asyncio
async def test_sqlite_migration_deduplicates_and_adds_quote_index():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE stock_quotes ("
                "id INTEGER PRIMARY KEY, symbol VARCHAR(20), source_timestamp DATETIME)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO stock_quotes (symbol, source_timestamp) VALUES "
                "('PSO', '2026-08-03 11:00:00'), ('PSO', '2026-08-03 11:00:00')"
            )
        )
        await _migrate_sqlite_schema(conn)
        count = (
            await conn.execute(text("SELECT COUNT(*) FROM stock_quotes"))
        ).scalar_one()
        indexes = (await conn.execute(text("PRAGMA index_list('stock_quotes')"))).all()
    await engine.dispose()

    assert count == 1
    assert any(row[1] == "uq_stock_quote_symbol_ts" and row[2] == 1 for row in indexes)
