from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine

from psx_data_hub.core.config import settings
from psx_data_hub.storage.models import Base

log = logging.getLogger("psx_data_hub.db")


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
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def _migrate_stock_quotes_unique(conn: AsyncConnection) -> None:
    """Ensure `stock_quotes` carries the UniqueConstraint(symbol, source_timestamp).

    SQLAlchemy's `create_all` only creates missing tables; it will not add a
    new UniqueConstraint to an existing SQLite table. We check `PRAGMA
    index_list` and, if the constraint is missing, rebuild the table via the
    standard SQLite recipe (copy-to-new + rename).
    """
    dialect = conn.dialect.name
    if dialect != "sqlite":
        # For real databases, this should be handled by a proper migration
        # tool (Alembic). Skip and let the operator manage it.
        return

    try:
        result = await conn.exec_driver_sql("PRAGMA index_list('stock_quotes')")
        indices = result.fetchall()
    except Exception:
        # Table does not exist yet — create_all will have made it fresh with
        # the constraint already in place.
        return

    has_unique = any(
        (row[1] or "").startswith("uq_stock_quote_symbol_ts") for row in indices
    )
    if has_unique:
        return

    log.info("adding UniqueConstraint(symbol, source_timestamp) to stock_quotes")
    # Standard SQLite pattern: table rebuild with new schema.
    await conn.exec_driver_sql(
        """
        CREATE TABLE stock_quotes__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol VARCHAR(20) NOT NULL,
            name VARCHAR(255),
            ltp FLOAT,
            change FLOAT,
            change_pct FLOAT,
            volume INTEGER,
            open_price FLOAT,
            high FLOAT,
            low FLOAT,
            close_price FLOAT,
            source_timestamp TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            source VARCHAR(80) DEFAULT 'psx',
            raw_payload JSON,
            CONSTRAINT uq_stock_quote_symbol_ts UNIQUE (symbol, source_timestamp)
        )
        """
    )
    await conn.exec_driver_sql(
        """
        INSERT INTO stock_quotes__new (
            id, symbol, name, ltp, change, change_pct, volume,
            open_price, high, low, close_price,
            source_timestamp, fetched_at, source, raw_payload
        )
        SELECT
            id, symbol, name, ltp, change, change_pct, volume,
            open_price, high, low, close_price,
            source_timestamp, fetched_at, source, raw_payload
        FROM stock_quotes
        WHERE 1 = 1
        GROUP BY symbol, source_timestamp
        """
    )
    await conn.exec_driver_sql("DROP TABLE stock_quotes")
    await conn.exec_driver_sql("ALTER TABLE stock_quotes__new RENAME TO stock_quotes")
    await conn.exec_driver_sql(
        "CREATE INDEX ix_stock_quotes_symbol ON stock_quotes (symbol)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX ix_stock_quotes_fetched_at ON stock_quotes (fetched_at)"
    )


async def init_db() -> None:
    """Create tables + apply the small set of hand-written migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_stock_quotes_unique(conn)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
