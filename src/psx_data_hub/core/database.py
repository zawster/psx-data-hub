from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from psx_data_hub.core.config import settings
from psx_data_hub.storage.models import Base

def _ensure_db_path() -> None:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        return

    if url.database:
        db_path = Path(url.database)
        if str(db_path).startswith("~"):
            db_path = db_path.expanduser()
        db_path = db_path.expanduser()
        if db_path.suffix:
            db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_db_path()
engine = create_async_engine(settings.database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)


async def _migrate_sqlite_schema(conn: AsyncConnection) -> None:
    """Apply idempotent schema upgrades that SQLite create_all cannot add."""
    if conn.dialect.name != "sqlite":
        return
    await conn.execute(
        text(
            """
            DELETE FROM stock_quotes
            WHERE source_timestamp IS NOT NULL
              AND id NOT IN (
                SELECT MIN(id)
                FROM stock_quotes
                WHERE source_timestamp IS NOT NULL
                GROUP BY symbol, source_timestamp
              )
            """
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_quote_symbol_ts "
            "ON stock_quotes (symbol, source_timestamp)"
        )
    )


async def _migrate_sqlite_schema(conn: AsyncConnection) -> None:
    """Apply idempotent schema upgrades that SQLite create_all cannot add."""
    if conn.dialect.name != "sqlite":
        return
    await conn.execute(
        text(
            """
            DELETE FROM stock_quotes
            WHERE source_timestamp IS NOT NULL
              AND id NOT IN (
                SELECT MIN(id)
                FROM stock_quotes
                WHERE source_timestamp IS NOT NULL
                GROUP BY symbol, source_timestamp
              )
            """
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_quote_symbol_ts "
            "ON stock_quotes (symbol, source_timestamp)"
        )
    )


async def init_db() -> None:
    """Create tables and apply idempotent SQLite schema upgrades."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_sqlite_schema(conn)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
