from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from psx_data_hub.providers.base import EodSnapshot, QuoteSnapshot, TimeseriesPoint
from psx_data_hub.storage import models


def _utcnow() -> datetime:
    """Return an aware UTC datetime. Prefer this over datetime.utcnow()."""
    return datetime.now(timezone.utc)


def is_stale(threshold_seconds: int, timestamp: datetime | None) -> bool:
    if not timestamp:
        return True
    if timestamp.tzinfo is None:
        # Treat naive timestamps as UTC — this is how everything gets stored.
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    now = _utcnow()
    return (now - timestamp).total_seconds() > threshold_seconds


class DataRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    # ---- Read ----
    async def get_symbol(self, symbol: str) -> models.Symbol | None:
        result = await self._session.execute(
            select(models.Symbol).where(models.Symbol.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def list_symbols(self, active_only: bool = True) -> list[models.Symbol]:
        stmt = select(models.Symbol)
        if active_only:
            stmt = stmt.where(models.Symbol.is_active.is_(True))
        stmt = stmt.order_by(models.Symbol.symbol.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_symbols(self, active_only: bool = True) -> int:
        stmt = select(func.count(models.Symbol.symbol))
        if active_only:
            stmt = stmt.where(models.Symbol.is_active.is_(True))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_latest_quote(self, symbol: str) -> models.StockQuote | None:
        stmt = (
            select(models.StockQuote)
            .where(models.StockQuote.symbol == symbol.upper())
            .order_by(models.StockQuote.fetched_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_latest_quotes(self) -> list[models.StockQuote]:
        """Return the latest quote for every symbol in ONE query.

        Replaces the N+1 loop that used to call `get_latest_quote` per symbol
        for the `companiesinprofit`, `companiesinloss` and `sectorgraph`
        endpoints (BUG-1).
        """
        latest_ts = (
            select(
                models.StockQuote.symbol.label("s"),
                func.max(models.StockQuote.fetched_at).label("mx"),
            )
            .group_by(models.StockQuote.symbol)
            .subquery()
        )
        stmt = select(models.StockQuote).join(
            latest_ts,
            and_(
                models.StockQuote.symbol == latest_ts.c.s,
                models.StockQuote.fetched_at == latest_ts.c.mx,
            ),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_quote_history(
        self,
        symbol: str,
        interval: str,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 500,
    ) -> list[models.HistoryPoint]:
        stmt = (
            select(models.HistoryPoint)
            .where(
                and_(
                    models.HistoryPoint.symbol == symbol.upper(),
                    models.HistoryPoint.interval == interval,
                )
            )
            .order_by(models.HistoryPoint.period_start.asc())
            .limit(limit)
        )
        if from_ts is not None:
            stmt = stmt.where(models.HistoryPoint.period_start >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(models.HistoryPoint.period_start <= to_ts)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_eod(
        self,
        symbol: str,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 500,
    ) -> list[models.EodRecord]:
        stmt = (
            select(models.EodRecord)
            .where(models.EodRecord.symbol == symbol.upper())
            .order_by(models.EodRecord.date.desc())
            .limit(limit)
        )
        if from_date is not None:
            stmt = stmt.where(models.EodRecord.date >= from_date)
        if to_date is not None:
            stmt = stmt.where(models.EodRecord.date <= to_date)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_market_snapshot(self) -> models.MarketSnapshot | None:
        result = await self._session.execute(
            select(models.MarketSnapshot).order_by(models.MarketSnapshot.fetched_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_market_timestamp(self) -> datetime | None:
        snapshot = await self.get_latest_market_snapshot()
        return snapshot.source_timestamp if snapshot else None

    # ---- Write ----
    async def upsert_symbol(
        self, symbol: str, name: str | None = None, sector: str | None = None
    ) -> models.Symbol:
        normalized = symbol.upper()
        row = await self.get_symbol(normalized)
        if row is None:
            row = models.Symbol(
                symbol=normalized,
                name=name,
                sector=sector,
                updated_at=_utcnow(),
            )
            self._session.add(row)
        else:
            if name:
                row.name = name
            if sector:
                row.sector = sector
            row.is_active = True
            row.updated_at = _utcnow()
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def upsert_symbols(self, symbols: Iterable[tuple[str, str | None]]) -> list[models.Symbol]:
        rows: list[models.Symbol] = []
        for symbol, name in symbols:
            rows.append(await self.upsert_symbol(symbol, name))
        return rows

    async def upsert_quote(self, snapshot: QuoteSnapshot) -> models.StockQuote:
        row = models.StockQuote(
            symbol=snapshot.symbol.upper(),
            name=snapshot.name,
            ltp=snapshot.ltp,
            change=snapshot.change,
            change_pct=snapshot.change_pct,
            volume=(
                int(snapshot.volume)
                if isinstance(snapshot.volume, (int, float))
                else None
            ),
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            close=snapshot.close,
            source_timestamp=snapshot.source_timestamp,
            source=snapshot.source,
            raw_payload=snapshot.raw,
            fetched_at=_utcnow(),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def upsert_market_snapshot(
        self, payload: dict, source_timestamp: datetime | None, source: str
    ) -> models.MarketSnapshot:
        row = models.MarketSnapshot(
            payload=payload,
            source_timestamp=source_timestamp,
            source=source,
            fetched_at=_utcnow(),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def delete_old_quotes(self, before: datetime) -> int:
        result = await self._session.execute(
            delete(models.StockQuote).where(models.StockQuote.fetched_at < before)
        )
        count = result.rowcount or 0
        await self._session.commit()
        return count

    async def upsert_history_points(self, points: Iterable[TimeseriesPoint]) -> int:
        """Insert-or-ignore history points.

        Uses SQLite ON CONFLICT to avoid the previous N+1 SELECT-then-INSERT
        pattern. Falls back to per-row insertion for other backends.
        """
        added = 0
        rows = [
            {
                "symbol": p.symbol.upper(),
                "interval": p.interval,
                "period_start": p.period_start,
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": (
                    int(p.volume) if isinstance(p.volume, (int, float)) else None
                ),
                "source_timestamp": p.source_timestamp,
                "source": p.source,
                "raw_payload": p.raw,
                "fetched_at": _utcnow(),
            }
            for p in points
        ]
        if not rows:
            return 0
        dialect = self._session.bind.dialect.name if self._session.bind else ""
        if dialect == "sqlite":
            stmt = sqlite_insert(models.HistoryPoint).values(rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["symbol", "interval", "period_start"]
            )
            result = await self._session.execute(stmt)
            added = result.rowcount or 0
        else:
            # Portable fallback — one row at a time.
            for row in rows:
                try:
                    self._session.add(models.HistoryPoint(**row))
                    await self._session.commit()
                    added += 1
                except Exception:
                    await self._session.rollback()
        await self._session.commit()
        return added

    async def upsert_eod_records(self, points: Iterable[EodSnapshot]) -> int:
        added = 0
        rows = [
            {
                "symbol": p.symbol.upper(),
                "date": p.date,
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": (
                    int(p.volume) if isinstance(p.volume, (int, float)) else None
                ),
                "source_timestamp": p.source_timestamp,
                "source": p.source,
                "raw_payload": p.raw,
                "fetched_at": _utcnow(),
            }
            for p in points
        ]
        if not rows:
            return 0
        dialect = self._session.bind.dialect.name if self._session.bind else ""
        if dialect == "sqlite":
            stmt = sqlite_insert(models.EodRecord).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "date"])
            result = await self._session.execute(stmt)
            added = result.rowcount or 0
        else:
            for row in rows:
                try:
                    self._session.add(models.EodRecord(**row))
                    await self._session.commit()
                    added += 1
                except Exception:
                    await self._session.rollback()
        await self._session.commit()
        return added
