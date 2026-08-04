from __future__ import annotations


def test_service_contract_off_mode(seeded_client_factory):
    with seeded_client_factory() as client:
        health = client.get("/v1/health")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["status"] == "ok"
        assert health_payload["data_delay_minutes"] == 5
        assert "data_source_notice" in health_payload
        assert health_payload["database"] == "ok"

        status = client.get("/v1/status")
        assert status.status_code == 200
        status_payload = status.json()
        assert status_payload["status"] == "ok"

        stocks = client.get("/v1/stocks")
        assert stocks.status_code == 200
        symbols = stocks.json()
        assert len(symbols) >= 3
        returned_symbols = {row["symbol"] for row in symbols}
        assert {"PSO", "OGDC", "HBL"}.issubset(returned_symbols)

        stock = client.get("/v1/stocks/PSO")
        assert stock.status_code == 200
        stock_payload = stock.json()
        assert stock_payload["symbol"] == "PSO"
        assert stock_payload["ltp"] == 325.25
        assert stock_payload["change"] == 5.75
        assert "delay" in stock_payload

        desc = client.get("/v1/stocks/PSO/description")
        assert desc.status_code == 200
        desc_payload = desc.json()
        assert desc_payload["symbol"] == "PSO"
        assert (
            desc_payload["sector"] == "Energy"
        )  # seeded via upsert_symbol(sector=...)

        # Bad interval is rejected (BUG-5)
        bad_interval = client.get(
            "/v1/stocks/PSO/history", params={"interval": "bogus"}
        )
        assert bad_interval.status_code == 422

        # int/eod are the only valid intervals now (matches PSX upstream)
        history = client.get(
            "/v1/stocks/PSO/history", params={"interval": "eod", "limit": 20}
        )
        assert history.status_code == 200

        eod = client.get("/v1/stocks/PSO/eod", params={"limit": 20})
        assert eod.status_code == 200
        rows = eod.json()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "PSO"

        # Reverse date range is rejected (BUG-9)
        reverse = client.get(
            "/v1/stocks/PSO/eod",
            params={"from": "2027-01-01", "to": "2025-01-01"},
        )
        assert reverse.status_code == 400

        # XSS-shaped symbol is rejected (BUG-6)
        bad_symbol = client.get("/v1/stocks/<script>")
        assert bad_symbol.status_code == 400

        market = client.get("/v1/market")
        assert market.status_code == 200
        market_payload = market.json()
        assert "indices" in market_payload
        assert market_payload["indices"][0]["symbol"] == "KSE100"
        assert market_payload["delay"]["source"] == "seed"

        indices = client.get("/v1/indices")
        assert indices.status_code == 200
        assert len(indices.json()["indices"]) == 2

        all_indices = client.get("/allindices")
        assert all_indices.status_code == 200
        assert all_indices.json()["delay"]["source"] == "seed"

        get_index = client.get("/getindex", params={"symbol": "KSE100"})
        assert get_index.status_code == 200
        assert get_index.json()["symbol"] == "KSE100"

        volume = client.get("/volume")
        assert volume.status_code == 200
        assert volume.json()["metric"] == "volume"
        assert volume.json()["value"] == 12500000
        assert volume.json()["delay"]["source"] == "seed"

        trades = client.get("/tradesinstockmarket")
        assert trades.status_code == 200
        assert trades.json()["metric"] == "trades_in_stock_market"
        assert trades.json()["value"] == 9876

        total_companies = client.get("/totalcompanies")
        assert total_companies.status_code == 200
        assert total_companies.json()["metric"] == "total_companies"
        assert total_companies.json()["value"] >= 3

        loss = client.get("/companiesinloss")
        assert loss.status_code == 200
        assert loss.json()["value"] == 1

        profit = client.get("/companiesinprofit")
        assert profit.status_code == 200
        assert profit.json()["value"] == 1

        sectors = client.get("/sectors")
        assert sectors.status_code == 200
        sector_payload = sectors.json()
        assert sector_payload["metric"] == "sectors"
        # Seed now labels sectors — expect at least one real sector plus possibly Unknown.
        assert sector_payload["count"] >= 1
        sector_names = {row["sector"] for row in sector_payload["items"]}
        assert "Energy" in sector_names

        graph = client.get("/sectorgraph")
        assert graph.status_code == 200
        assert graph.json()["metric"] == "sectorgraph"

        company_data = client.get("/PSO/getalldata")
        assert company_data.status_code == 200
        assert company_data.json()["symbol"] == "PSO"

        description = client.get("/PSO/description")
        assert description.status_code == 200
        assert description.json()["description"] is None

        equity_data = client.get("/PSO/equitydata")
        assert equity_data.status_code == 200
        assert equity_data.json()["symbol"] == "PSO"

        for path in [
            "/v1/health",
            "/v1/status",
            "/v1/stocks",
            "/v1/indices",
            "/status",
        ]:
            get_response = client.get(path)
            head = client.head(path)
            assert head.status_code == 200
            assert head.content == b""
            assert int(head.headers["content-length"]) == len(get_response.content)


def test_compat_token_flow(seeded_client_factory):
    with seeded_client_factory() as client:
        token_resp = client.post(
            "/token", data={"username": "demo", "password": "demo"}
        )
        assert token_resp.status_code == 200
        token = token_resp.json()["access_token"]
        assert isinstance(token, str) and len(token) > 20

        valid_check = client.get(
            "/token-check", headers={"Authorization": f"Bearer {token}"}
        )
        assert valid_check.status_code == 200
        assert valid_check.json()["message"] == "You are authenticated!"

        assert client.get("/token-check").status_code == 401

        bad_token = client.get(
            "/token-check", headers={"Authorization": "Bearer invalid.token.value"}
        )
        assert bad_token.status_code == 401

        bad_login = client.post(
            "/token", data={"username": "demo", "password": "wrong"}
        )
        assert bad_login.status_code == 401


def test_jwt_secret_rejected_in_non_local(monkeypatch):
    """BUG-3: the app must refuse to boot with the default JWT secret outside local env."""
    import importlib

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.delenv("DEBUG", raising=False)

    import psx_data_hub.core.config as cfg

    try:
        importlib.reload(cfg)
        boot_error = None
    except Exception as exc:
        boot_error = exc

    assert boot_error is not None, (
        "config must reject default JWT secret when ENV != local"
    )
    # Reset for other tests.
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
    importlib.reload(cfg)
