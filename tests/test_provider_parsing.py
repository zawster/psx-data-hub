from __future__ import annotations

import httpx
import pytest

from psx_data_hub.providers.base import ProviderParseError
from psx_data_hub.providers.psx_dps_provider import PsxDpsProvider


@pytest.mark.asyncio
async def test_market_overview_combines_authoritative_psx_pages(monkeypatch):
    market_watch = """
    <table><tr><th>SYMBOL</th><th>SECTOR</th><th>LISTED IN</th><th>LDCP</th>
    <th>OPEN</th><th>HIGH</th><th>LOW</th><th>CURRENT</th><th>CHANGE</th>
    <th>CHANGE (%)</th><th>VOLUME</th></tr>
    <tr><td>PSO</td><td>0821</td><td>KSE100</td><td>347.49</td><td>350.50</td>
    <td>356.37</td><td>349.00</td><td>353.49</td><td>6.00</td><td>1.73%</td>
    <td>2,944,798</td></tr></table>
    """
    indices = """
    <table><tr><th>Index</th><th>High</th><th>Low</th><th>Current</th>
    <th>Change</th><th>% Change</th></tr>
    <tr><td>KSE100</td><td>178,768.83</td><td>178,023.65</td><td>178,129.37</td>
    <td>-70.65</td><td>-0.04%</td></tr></table>
    """
    status = """
    <div data-key="REG"><a class="markets__item">
      <div class="markets__item__stat"><div class="markets__item__stat__label">State</div><div>Open</div></div>
      <div class="markets__item__stat"><div class="markets__item__stat__label">Trades</div><div>122,772</div></div>
      <div class="markets__item__stat"><div class="markets__item__stat__label">Volume</div><div>246,453,921</div></div>
      <div class="markets__item__stat"><div class="markets__item__stat__label">Value</div><div>9,368,281,234.67</div></div>
    </a></div>
    """
    sectors = """
    <table><tr><th>Sector Code</th><th>Sector Name</th><th>Turnover</th></tr>
    <tr><td>0821</td><td>OIL &amp; GAS MARKETING COMPANIES</td><td>2,944,798</td></tr>
    </table>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        pages = {
            "/market-watch": market_watch,
            "/indices": indices,
            "/": status,
            "/sector-summary": sectors,
        }
        return httpx.Response(
            200, text=pages[request.url.path], headers={"content-type": "text/html"}
        )

    monkeypatch.setattr(
        "psx_data_hub.providers.psx_dps_provider.settings.provider_market_summary_url",
        "https://dps.test/market-watch",
    )
    monkeypatch.setattr(
        "psx_data_hub.providers.psx_dps_provider.settings.provider_indices_url",
        "https://dps.test/indices",
    )
    monkeypatch.setattr(
        "psx_data_hub.providers.psx_dps_provider.settings.provider_market_status_url",
        "https://dps.test/",
    )
    monkeypatch.setattr(
        "psx_data_hub.providers.psx_dps_provider.settings.provider_sector_summary_url",
        "https://dps.test/sector-summary",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload, fetched_at = await PsxDpsProvider(client).fetch_market_overview()

    assert fetched_at is not None
    assert payload["tickers"][0]["current"] == 353.49
    assert payload["tickers"][0]["sector_code"] == "0821"
    assert payload["tickers"][0]["sector"] == "OIL & GAS MARKETING COMPANIES"
    assert payload["indices"][0]["symbol"] == "KSE100"
    assert payload["indices"][0]["value"] == 178129.37
    assert payload["market_status"] == "open"
    assert payload["trades"] == 122772
    assert payload["total_volume"] == 246453921


def test_timeseries_rejects_schema_drift():
    provider = PsxDpsProvider()
    with pytest.raises(ProviderParseError, match="'data' must be a list"):
        provider._parse_timeseries_json("PSO", "int", {"status": 1, "points": []})
