from __future__ import annotations


def test_service_contract_off_mode(seeded_client_factory):
    with seeded_client_factory() as client:
        health = client.get("/v1/health")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["status"] == "ok"
        assert health_payload["data_delay_minutes"] == 5
        assert "data_source_notice" in health_payload

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

        stock = client.get("/v1/stocks/company/PSO")
        assert stock.status_code == 200
        stock_payload = stock.json()
        assert stock_payload["symbol"] == "PSO"
        assert stock_payload["ltp"] == 325.25
        assert stock_payload["change"] == 5.75
        assert "delay" in stock_payload

        desc = client.get("/v1/stocks/PSO/description")
        assert desc.status_code == 200
        assert desc.json()["symbol"] == "PSO"

        equity = client.get("/v1/stocks/PSO/equity")
        assert equity.status_code == 200
        assert equity.json()["close"] == 325.0

        history = client.get("/v1/stocks/PSO/history", params={"interval": "5m", "limit": 20})
        assert history.status_code == 200
        points = history.json()
        assert len(points) == 2
        assert points[0]["interval"] == "5m"

        eod = client.get("/v1/stocks/PSO/eod", params={"limit": 20})
        assert eod.status_code == 200
        rows = eod.json()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "PSO"

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
        assert sector_payload["count"] >= 3

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


def test_compat_token_flow(seeded_client_factory):
    with seeded_client_factory() as client:
        token_resp = client.post("/token", data={"username": "demo", "password": "demo"})
        assert token_resp.status_code == 200
        token = token_resp.json()["access_token"]
        assert isinstance(token, str) and len(token) > 20

        valid_check = client.get("/token-check", headers={"Authorization": f"Bearer {token}"})
        assert valid_check.status_code == 200
        assert valid_check.json()["message"] == "You are authenticated!"

        assert client.get("/token-check").status_code == 401

        bad_token = client.get("/token-check", headers={"Authorization": "Bearer invalid.token.value"})
        assert bad_token.status_code == 401

        bad_login = client.post("/token", data={"username": "demo", "password": "wrong"})
        assert bad_login.status_code == 401
