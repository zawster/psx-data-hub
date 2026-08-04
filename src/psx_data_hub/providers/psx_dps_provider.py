from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
import httpx

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


_MARKET_WATCH_HEADERS = {
    "symbol": {"symbol", "scrip"},
    "sector": {"sector"},
    "listed_in": {"listed in", "indices", "index"},
    "ldcp": {"ldcp", "last day close price", "previous close"},
    "open": {"open", "opening"},
    "high": {"high"},
    "low": {"low"},
    "current": {"current", "ltp", "last"},
    "change": {"change", "chg"},
    "change_pct": {"change (%)", "change%", "change percent", "%chg"},
    "volume": {"volume", "vol", "tradevolume"},
}


def _num(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    raw = str(value).strip().replace(",", "")
    if not raw or raw in {"-", "N/A", "NA", "None"}:
        return None
    if raw.endswith("%"):
        raw = raw[:-1].strip()
    try:
        if "." in raw or "e" in raw.lower():
            return float(raw)
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except Exception:
            return None


class PsxDpsProvider(StockMarketDataProvider):
    """Fetches PSX delayed data from `dps.psx.com.pk`.

    Live URLs (verified 2026-08-03):
      * `/market-watch` — one HTML table with a row per listed symbol. Source of every quote.
      * `/timeseries/int/{sym}` — intraday JSON: `{status:1, data:[[unix_ts, price, volume], ...]}`.
      * `/timeseries/eod/{sym}` — end-of-day JSON, same shape (with an extra column).

    Individual `/company/{sym}` pages are static company profiles and contain
    no price data — they are not scraped.
    """

    source = "dps.psx.com.pk"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "psx-data-hub/0.2.0 (+https://github.com/zawster/psx-data-hub)"},
        )
        self._latest_watch: dict[str, dict[str, Any]] = {}

    async def close(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def _fetch(self, url: str) -> tuple[str, Any]:
        try:
            response = await self._client.get(url)
        except Exception as exc:
            raise ProviderTemporaryError(f"{type(exc).__name__} for {url}: {exc}") from exc
        if response.status_code == 404:
            raise ProviderPermanentError(f"Not found: {url}")
        try:
            response.raise_for_status()
        except Exception as exc:
            raise ProviderTemporaryError(f"{type(exc).__name__} for {url}: {exc}") from exc

        content_type = (response.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            return "json", response.json()
        body = response.text
        stripped = body.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                return "json", response.json()
            except Exception:
                pass
        return "html", body

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()

    def _classify_header(self, headers: list[str]) -> dict[str, int]:
        idx: dict[str, int] = {}
        for i, raw in enumerate(headers):
            label = raw.strip().lower()
            for key, aliases in _MARKET_WATCH_HEADERS.items():
                if key in idx:
                    continue
                if label in aliases:
                    idx[key] = i
                    break
        return idx

    def _parse_market_watch_html(self, html: str) -> tuple[list[dict[str, Any]], datetime]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if table is None:
            raise ProviderParseError("market-watch: no <table> found")

        rows = table.find_all("tr")
        if not rows:
            raise ProviderParseError("market-watch: table has no rows")

        header_cells = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        idx = self._classify_header(header_cells)
        if "symbol" not in idx or "current" not in idx:
            raise ProviderParseError(
                f"market-watch: could not map required columns from headers={header_cells}"
            )

        parsed: list[dict[str, Any]] = []
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < max(idx.values()) + 1:
                continue
            symbol_raw = cells[idx["symbol"]].strip().upper()
            if not symbol_raw or not re.fullmatch(r"[A-Z0-9._-]{1,20}", symbol_raw):
                continue

            ltp = _num(cells[idx["current"]])
            if ltp is None:
                # skip rows without a current price (halted / suspended)
                continue

            def col(key: str) -> Any:
                i = idx.get(key)
                return cells[i] if i is not None and i < len(cells) else None

            parsed.append(
                {
                    "symbol": symbol_raw,
                    "sector": (col("sector") or "").strip() or None,
                    "listed_in": (col("listed_in") or "").strip() or None,
                    "ldcp": _num(col("ldcp")),
                    "open": _num(col("open")),
                    "high": _num(col("high")),
                    "low": _num(col("low")),
                    "current": ltp,
                    "change": _num(col("change")),
                    "change_pct": _num(col("change_pct")),
                    "volume": _num(col("volume")),
                }
            )

        # We don't have a source timestamp in the HTML; use "now" as fetched_at.
        return parsed, datetime.now(timezone.utc)

    def _parse_indices_html(self, html: str) -> list[dict[str, Any]]:
        """Parse the standalone `/indices` page.

        The page has a table with header `Index | High | Low | Current | Change | % Change`
        and one row per market index (KSE100, KSE100PR, ALLSHR, KSE30, KMI30, …).
        """
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if table is None:
            return []
        rows = table.find_all("tr")
        if len(rows) < 2:
            return []
        # Column order is fixed on PSX's page today; check header just to be safe.
        header = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        expected_prefix = ["index", "high", "low", "current", "change"]
        if header[: len(expected_prefix)] != expected_prefix:
            return []

        indices: list[dict[str, Any]] = []
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 6:
                continue
            symbol = cells[0].strip().upper()
            if not re.fullmatch(r"[A-Z0-9._-]{1,32}", symbol):
                continue
            indices.append(
                {
                    "symbol": symbol,
                    "name": symbol,
                    "high": _num(cells[1]),
                    "low": _num(cells[2]),
                    "value": _num(cells[3]),
                    "change": _num(cells[4]),
                    "changePct": _num(cells[5]),
                    "change_pct": _num(cells[5]),
                }
            )
        return indices

    async def _fetch_indices(self) -> list[dict[str, Any]]:
        """Fetch the `/indices` page. Returns [] on any failure — indices are
        a soft dependency of market overview."""
        try:
            base = settings.provider_base_url.rstrip("/")
            kind, payload = await self._fetch(f"{base}/indices")
        except Exception:
            return []
        if kind != "html":
            return []
        return self._parse_indices_html(str(payload))

    async def fetch_market_overview(self) -> tuple[dict[str, Any], datetime | None]:
        kind, payload = await self._fetch(settings.provider_market_summary_url)
        if kind != "html":
            raise ProviderParseError(
                "market-watch: expected HTML response, got json"
            )
        rows, ts = self._parse_market_watch_html(str(payload))

        # Cache the parsed rows so per-symbol quote lookups can be served
        # from the same fetch instead of re-scraping.
        self._latest_watch = {row["symbol"]: row for row in rows}

        indices = await self._fetch_indices()
        total_volume = sum(
            int(row["volume"])
            for row in rows
            if isinstance(row.get("volume"), (int, float))
        )

        # `market_status` and `trades` are NOT available from /market-watch. We
        # intentionally return "unknown" and null instead of guessing — the
        # previous code inferred "open" whenever any row was present and
        # counted ticker rows as trades, which was wrong after market close.
        return (
            {
                "indices": indices,
                "tickers": rows,
                "total_volume": total_volume,
                "trades": None,
                "market_status": "unknown",
                "status": "unknown",
            },
            ts,
        )

    def _row_to_quote(self, row: dict[str, Any]) -> QuoteSnapshot:
        return QuoteSnapshot(
            symbol=row["symbol"],
            source=self.source,
            name=None,  # market-watch does not include a full company name
            ltp=row.get("current"),
            change=row.get("change"),
            change_pct=row.get("change_pct"),
            volume=row.get("volume") if isinstance(row.get("volume"), (int, float)) else None,
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("ldcp"),  # LDCP = last-day close price (previous close)
            source_timestamp=datetime.now(timezone.utc),
            raw=dict(row),
        )

    def latest_watch_rows(self) -> list[dict[str, Any]]:
        """Rows from the most recent market-watch fetch (unfiltered)."""
        return list(self._latest_watch.values())

    async def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        symbol = self._normalize_symbol(symbol)
        row = self._latest_watch.get(symbol)
        if row is None:
            # If the cache is empty (no market-watch pulled yet), pull it now.
            await self.fetch_market_overview()
            row = self._latest_watch.get(symbol)
        if row is None:
            raise ProviderPermanentError(f"symbol '{symbol}' not present in PSX market-watch")
        return self._row_to_quote(row)

    async def fetch_timeseries(self, symbol: str, interval: str) -> list[TimeseriesPoint]:
        """Fetch intraday or EOD time series for a symbol.

        `interval` must be one of `int` (intraday) or `eod`.
        The upstream JSON shape is `{"status":1,"data":[[unix_ts, price, volume, ...], ...]}`.
        """
        symbol = self._normalize_symbol(symbol)
        interval = interval.strip().lower()
        if interval not in {"int", "eod"}:
            raise ProviderPermanentError(
                f"interval '{interval}' not supported; use 'int' or 'eod'"
            )

        url = settings.provider_timeseries_url_template.format(
            provider_base_url=settings.provider_base_url.rstrip("/"),
            interval=interval,
            symbol=symbol,
        )
        kind, payload = await self._fetch(url)
        if kind != "json":
            raise ProviderParseError(f"timeseries: expected JSON, got {kind}")

        return self._parse_timeseries_json(symbol, interval, payload)

    def _parse_timeseries_json(
        self, symbol: str, interval: str, payload: Any
    ) -> list[TimeseriesPoint]:
        # Anything that's not a dict with a `data` list is malformed. Surface
        # that as a parse error so upstream schema drift is noisy rather than
        # silently returning [] (round-2 review finding).
        if not isinstance(payload, dict):
            raise ProviderParseError(
                f"timeseries: unexpected payload type {type(payload).__name__}"
            )
        if "data" not in payload:
            raise ProviderParseError(
                f"timeseries: response missing 'data' key; keys={list(payload)[:5]}"
            )
        if payload.get("status") not in (1, "1", "ok", True, None):
            # Provider explicitly reported an error status — legitimate empty.
            return []
        raw_rows = payload.get("data")
        if not isinstance(raw_rows, list):
            raise ProviderParseError(
                f"timeseries: 'data' is {type(raw_rows).__name__}, expected list"
            )

        points: list[TimeseriesPoint] = []
        for row in raw_rows:
            if not isinstance(row, list) or not row:
                continue
            try:
                ts = datetime.fromtimestamp(float(row[0]), tz=timezone.utc)
            except Exception:
                continue
            price = _num(row[1]) if len(row) > 1 else None
            volume = _num(row[2]) if len(row) > 2 else None
            # EOD rows carry an extra column (previous close). Ignore for now.
            open_ = high = low = None
            close = price
            points.append(
                TimeseriesPoint(
                    symbol=symbol,
                    interval=interval,
                    period_start=ts,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=int(volume) if isinstance(volume, (int, float)) else None,
                    source_timestamp=ts,
                    source=self.source,
                    raw={"row": row},
                )
            )
        points.sort(key=lambda p: p.period_start)
        return points

    async def fetch_eod(
        self,
        symbol: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[EodSnapshot]:
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


