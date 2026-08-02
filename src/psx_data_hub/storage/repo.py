from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from psx_data_hub.providers.base import EodSnapshot, QuoteSnapshot, TimeseriesPoint
from psx_data_hub.storage import models


def is_stale(threshold_seconds: int, timestamp: datetime | None) -> bool:
    if not timestamp:
        return True
    now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.utcnow()
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
    async def upsert_symbol(self, symbol: str, name: str | None = None) -> models.Symbol:
        normalized = symbol.upper()
        row = await self.get_symbol(normalized)
        if row is None:
            row = models.Symbol(symbol=normalized, name=name, updated_at=datetime.utcnow())
            self._session.add(row)
        else:
            if name:
                row.name = name
            row.is_active = True
            row.updated_at = datetime.utcnow()
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
            volume=snapshot.volume,
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            close=snapshot.close,
            source_timestamp=snapshot.source_timestamp,
            source=snapshot.source,
            raw_payload=snapshot.raw,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def upsert_market_snapshot(self, payload: dict, source_timestamp: datetime | None, source: str) -> models.MarketSnapshot:
        row = models.MarketSnapshot(
            payload=payload,
            source_timestamp=source_timestamp,
            source=source,
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
        added = 0
        for point in points:
            existing = await self._session.execute(
                select(models.HistoryPoint.id).where(
                    models.HistoryPoint.symbol == point.symbol.upper(),
                    models.HistoryPoint.interval == point.interval,
                    models.HistoryPoint.period_start == point.period_start,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            row = models.HistoryPoint(
                symbol=point.symbol.upper(),
                interval=point.interval,
                period_start=point.period_start,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
                source_timestamp=point.source_timestamp,
                source=point.source,
                raw_payload=point.raw,
            )
            self._session.add(row)
            added += 1
        await self._session.commit()
        return added

    async def upsert_eod_records(self, points: Iterable[EodSnapshot]) -> int:
        added = 0
        for point in points:
            existing = await self._session.execute(
                select(models.EodRecord.id).where(
                    models.EodRecord.symbol == point.symbol.upper(),
                    models.EodRecord.date == point.date,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            row = models.EodRecord(
                symbol=point.symbol.upper(),
                date=point.date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
                source_timestamp=point.source_timestamp,
                source=point.source,
                raw_payload=point.raw,
            )
            self._session.add(row)
            added += 1
        await self._session.commit()
        return added
