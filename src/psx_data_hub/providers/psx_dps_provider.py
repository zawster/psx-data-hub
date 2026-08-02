from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable

from bs4 import BeautifulSoup
import httpx
from dateutil.parser import parse as parse_datetime

from psx_data_hub.core.config import settings
from psx_data_hub.providers.base import (
    EodSnapshot,
    ProviderParseError,
    ProviderPermanentError,
    ProviderTemporaryError,
    QuoteSnapshot,
    StockMarketDataProvider,
    TimeseriesPoint,
)


class PsxDpsProvider(StockMarketDataProvider):
    """Public-source provider for PSX DPS pages.

    This provider is explicitly delay-first and built to survive light payload drift.
    """

    source = "dps.psx.com.pk"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "psx-data-hub/0.1.0 (+https://github.com)"},
        )

    async def close(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    @staticmethod
    def _num(value: Any) -> float | int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        raw = str(value).replace(",", "").strip()
        if not raw or raw in {"-", "N/A", "NA", "None"}:
            return None
        try:
            if raw.endswith("%"):
                raw = raw[:-1]
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except Exception:
                return None

    @staticmethod
    def _date(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except Exception:
                return None
        try:
            parsed = parse_datetime(str(value), fuzzy=True)
            return parsed
        except Exception:
            return None

    @staticmethod
    def _first(payload: Any, *candidates: str) -> Any:
        if not isinstance(payload, dict):
            return None
        for key in candidates:
            if key in payload and payload[key] not in (None, "", "NA", "N/A", "-"):
                return payload[key]
        return None

    def _flatten_dict(self, payload: dict[str, Any] | list[Any] | Any) -> Iterable[dict[str, Any]]:
        if isinstance(payload, dict):
            yield payload
            for value in payload.values():
                yield from self._flatten_dict(value)
            return
        if isinstance(payload, list):
            for item in payload:
                yield from self._flatten_dict(item)

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper().replace("-", "_")

    def _to_error(self, exc: Exception, url: str) -> str:
        return f"{type(exc).__name__} for {url}: {exc}"

    def _json_like(self, value: str) -> bool:
        value = value.strip()
        return value.startswith("{") or value.startswith("[")

    async def _fetch(self, url: str) -> tuple[str, Any]:
        try:
            response = await self._client.get(url)
        except Exception as exc:
            raise ProviderTemporaryError(self._to_error(exc, url))
        if response.status_code == 404:
            raise ProviderPermanentError(f"Not found: {url}")
        try:
            response.raise_for_status()
        except Exception as exc:
            raise ProviderTemporaryError(self._to_error(exc, url))

        content_type = (response.headers.get("content-type") or "").lower()
        body = response.text
        if "application/json" in content_type:
            return "json", response.json()
        if self._json_like(body):
            try:
                return "json", response.json()
            except Exception:
                pass
        return "html", body

    def _extract_json_from_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict[str, Any]] = []
        candidates = soup.find_all("script")
        for tag in candidates:
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            if "window.__NUXT__" in text or "__NUXT__" in text:
                matches = re.findall(r"(?:window\.)?__NUXT__\s*=\s*(\{.*\});", text, flags=re.S)
                for match in matches:
                    try:
                        payload = json.loads(match)
                        if isinstance(payload, dict):
                            results.append(payload)
                    except Exception:
                        continue
                continue
            if "application/json" in (tag.get("type") or "").lower():
                try:
                    payload = json.loads(text)
                    if isinstance(payload, (dict, list)):
                        results.append(payload if isinstance(payload, dict) else {"data": payload})
                except Exception:
                    continue
            match = re.search(r"\{\s*\"data\"\s*:\s*\[.*\]\s*\}\s*$", text, re.S)
            if match:
                try:
                    payload = json.loads(match.group(0))
                    if isinstance(payload, dict):
                        results.append(payload)
                except Exception:
                    continue

        if not results:
            # secondary heuristics for pages that store JSON in HTML attrs
            marker_pattern = re.compile(r"data-json=\"([^\"]+)\"")
            for marker in marker_pattern.findall(html):
                try:
                    payload = json.loads(marker)
                    if isinstance(payload, dict):
                        results.append(payload)
                except Exception:
                    continue
        return results

    def _pick_rows(self, payload: Any) -> tuple[dict[str, Any] | None, datetime | None]:
        if not isinstance(payload, dict):
            return None, None
        data = self._first(payload, "data", "result", "payload", "response")
        if isinstance(data, dict):
            ts = self._date(self._first(data, "timestamp", "time", "asOf"))
            if isinstance(data.get("data"), (dict, list)):
                inner = self._first(data, "data")
                if isinstance(inner, list):
                    for row in inner:
                        if isinstance(row, dict):
                            return row, ts
                if isinstance(inner, dict):
                    return inner, ts
            return data, ts
        if isinstance(data, list) and data:
            if isinstance(data[0], dict):
                return data[0], self._date(self._first(data[0], "timestamp", "time", "asOf"))
        if isinstance(data, list):
            return {"data": data}, None
        return payload, self._date(self._first(payload, "timestamp", "time", "asOf"))

    async def fetch_market_overview(self) -> tuple[dict[str, Any], datetime | None]:
        kind, payload = await self._fetch(settings.provider_market_summary_url)
        source_ts: datetime | None = None
        if kind == "json":
            if isinstance(payload, list):
                return {"indices": payload}, None
            if isinstance(payload, dict):
                source_ts = self._date(self._first(payload, "timestamp", "time", "asOf", "updatedAt"))
                return payload, source_ts
            raise ProviderParseError("market summary returned unsupported json type")

        html = str(payload)
        extracted = self._extract_json_from_html(html)
        if extracted:
            for item in extracted:
                row, row_ts = self._pick_rows(item)
                if isinstance(row, dict):
                    source_ts = source_ts or row_ts
                    return {"extracted": row, "raw": row}, source_ts
            if extracted and isinstance(extracted[0], dict) and "indices" in extracted[0]:
                return extracted[0], None

        # fallback: return a best effort index of visible rows
        soup = BeautifulSoup(html, "lxml")
        data = {"indices": []}
        for row in soup.select("table tr"):
            cols = [col.get_text(" ", strip=True) for col in row.find_all(["td", "th"])]
            if len(cols) >= 2:
                data["indices"].append({"name": cols[0], "value": self._num(cols[1])})
        return data, source_ts or datetime.utcnow()

    async def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        symbol = self._normalize_symbol(symbol)
        candidate_urls = [settings.provider_quote_url_template.format(symbol=symbol)]
        for url in candidate_urls:
            kind, payload = await self._fetch(url)
            if kind == "json" and isinstance(payload, (dict, list)):
                return self._parse_json_quote(symbol, payload)
            if kind == "html":
                quote = self._parse_html_quote(symbol, str(payload))
                if quote and quote.ltp is not None:
                    return quote

        raise ProviderParseError(f"Could not parse quote from response for {symbol}")

    async def fetch_timeseries(self, symbol: str, interval: str) -> list[TimeseriesPoint]:
        symbol = self._normalize_symbol(symbol)
        interval = interval.lower()
        urls = [settings.provider_timeseries_url_template.format(symbol=symbol, interval=interval)]
        # PSX endpoints are inconsistent; attempt a fallback shape.
        urls.append(f"{settings.provider_base_url}/timeseries/{interval}/{symbol}")
        urls.append(f"{settings.provider_base_url}/company/{symbol}/timeseries/{interval}/")
        for url in urls:
            kind, payload = await self._fetch(url)
            if kind == "json":
                points = self._parse_timeseries_json(symbol, interval, payload)
                if points:
                    return points
            if kind == "html":
                points = self._parse_timeseries_html(symbol, interval, str(payload))
                if points:
                    return points
        return []

    async def fetch_eod(self, symbol: str, from_date=None, to_date=None) -> list[EodSnapshot]:
        points = await self.fetch_timeseries(symbol, interval="eod")
        output: list[EodSnapshot] = []
        for point in points:
            row_date = point.period_start.date()
            if from_date is not None and row_date < from_date:
                continue
            if to_date is not None and row_date > to_date:
                continue
            output.append(
                EodSnapshot(
                    symbol=point.symbol,
                    date=row_date,
                    open=point.open,
                    high=point.high,
                    low=point.low,
                    close=point.close,
                    volume=point.volume,
                    source_timestamp=point.source_timestamp,
                    source=point.source,
                    raw=point.raw,
                )
            )
        return output

    def _parse_json_quote(self, symbol: str, payload: dict[str, Any] | list[Any]) -> QuoteSnapshot:
        # Handle array payloads as "first item wins", then fallback object-level fields.
        if isinstance(payload, list):
            if not payload:
                raise ProviderParseError(f"quote payload empty for {symbol}")
            payload_dict = {}
            for item in payload:
                if isinstance(item, dict) and str(item.get("symbol", "")).upper() == symbol:
                    payload_dict = item
                    break
            if not payload_dict and isinstance(payload[0], dict):
                payload_dict = payload[0]
            payload = payload_dict

        if not isinstance(payload, dict):
            raise ProviderParseError(f"unexpected quote payload type for {symbol}: {type(payload)}")

        row, row_ts = self._pick_rows(payload)
        if row is None or not isinstance(row, dict):
            row = payload

        row_ts = row_ts or self._date(self._first(row, "timestamp", "time", "asOf", "dateTime"))
        return QuoteSnapshot(
            symbol=symbol,
            source=self.source,
            name=self._first(row, "companyName", "name", "company_name", "symbolName"),
            ltp=self._num(self._first(row, "ltp", "last", "lastPrice", "close", "trdPrc")),
            change=self._num(self._first(row, "change", "changeAmt", "chng", "difference")),
            change_pct=self._num(self._first(row, "changePct", "change_percent", "pctChange", "p_change")),
            volume=self._num(self._first(row, "volume", "tradeVol", "vol", "tradeVolume")),
            open=self._num(self._first(row, "open", "openPrice", "opening")),
            high=self._num(self._first(row, "high", "highPrice", "max")),
            low=self._num(self._first(row, "low", "lowPrice", "min")),
            close=self._num(self._first(row, "close", "closePrice", "ltp", "tradePrice")),
            source_timestamp=row_ts,
            raw=dict(row),
        )

    def _parse_timeseries_json(
        self,
        symbol: str,
        interval: str,
        payload: Any,
    ) -> list[TimeseriesPoint]:
        points: list[TimeseriesPoint] = []
        raw_rows: list[Any] = []
        if isinstance(payload, list):
            raw_rows = payload
        elif isinstance(payload, dict):
            data = self._first(payload, "data", "result", "rows")
            if isinstance(data, list):
                raw_rows = data
            elif isinstance(data, dict):
                rows = data.get("rows")
                if isinstance(rows, list):
                    raw_rows = rows

        if not raw_rows and isinstance(payload, dict):
            # flatten nested dicts and try any list-of-dicts
            for candidate in self._flatten_dict(payload):
                candidate_data = self._first(candidate, "data", "rows", "result")
                if isinstance(candidate_data, list):
                    raw_rows = candidate_data
                    break

        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            ts = self._date(self._first(row, "time", "timestamp", "date", "datetime"))
            if ts is None:
                continue
            points.append(
                TimeseriesPoint(
                    symbol=symbol,
                    interval=interval,
                    period_start=ts,
                    open=self._num(self._first(row, "open", "o")),
                    high=self._num(self._first(row, "high", "h")),
                    low=self._num(self._first(row, "low", "l")),
                    close=self._num(self._first(row, "close", "c", "ltp")),
                    volume=self._num(self._first(row, "volume", "v", "tradeVolume")),
                    source_timestamp=ts,
                    source=self.source,
                    raw=row,
                )
            )
        return sorted(points, key=lambda item: item.period_start)

    def _parse_timeseries_html(self, symbol: str, interval: str, html: str) -> list[TimeseriesPoint]:
        soup = BeautifulSoup(html, "lxml")
        points: list[TimeseriesPoint] = []
        for row in soup.select("table tr"):
            cols = [col.get_text(" ", strip=True) for col in row.find_all(["td", "th"])]
            if len(cols) < 5:
                continue
            ts = self._date(cols[0])
            if ts is None:
                continue
            values = [self._num(col) for col in cols[1:6]]
            if len(values) < 5:
                continue
            open_, high, low, close, volume = values[0], values[1], values[2], values[3], values[4]
            points.append(
                TimeseriesPoint(
                    symbol=symbol,
                    interval=interval,
                    period_start=ts,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=int(volume) if isinstance(volume, float) else volume,
                    source_timestamp=ts,
                    source=self.source,
                    raw={"row": cols},
                )
            )
        return sorted(points, key=lambda item: item.period_start)

    def _parse_html_quote(self, symbol: str, html: str) -> QuoteSnapshot:
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tr")
        fields: dict[str, Any] = {}
        text_rows = []
        for row in rows:
            cols = [col.get_text(" ", strip=True) for col in row.find_all(["th", "td"])]
            if len(cols) >= 2:
                fields[cols[0].strip().lower()] = cols[1].strip()
            text_rows.extend(cols)

        raw: dict[str, Any] = {"raw_rows": text_rows[:200]}
        title = (soup.find("h1") or soup.find("title") or None)
        name = title.get_text(" ", strip=True) if title else None
        ts = self._date(self._first(fields, "time", "timestamp", "updated"))

        return QuoteSnapshot(
            symbol=symbol,
            source=self.source,
            name=fields.get("company") or fields.get("company name") or name,
            ltp=self._num(self._first(fields, "ltp", "last", "price", "trade")),
            change=self._num(self._first(fields, "change", "chg")),
            change_pct=self._num(self._first(fields, "change percentage", "change %", "percent")),
            volume=self._num(self._first(fields, "volume", "volume traded", "traded volume")),
            open=self._num(self._first(fields, "open", "open price")),
            high=self._num(self._first(fields, "high", "high price")),
            low=self._num(self._first(fields, "low", "low price")),
            close=self._num(self._first(fields, "close", "close price", "ltp")),
            source_timestamp=ts or datetime.utcnow(),
            raw=raw,
        )
