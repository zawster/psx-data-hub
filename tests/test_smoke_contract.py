from __future__ import annotations

import os

import httpx
import pytest


def test_smoke_contract():
    base_url = os.getenv("PSX_API_BASE_URL")
    if not base_url:
        pytest.skip("PSX_API_BASE_URL is not set; this is a docker smoke test")

    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        health = client.get("/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        status = client.get("/v1/status")
        assert status.status_code == 200

        stock_list = client.get("/v1/stocks/symbols")
        assert stock_list.status_code == 200
        assert isinstance(stock_list.json(), list)

        status_root = client.get("/status")
        assert status_root.status_code in {200, 401}

        token = client.post("/token", data={"username": "demo", "password": "demo"})
        assert token.status_code == 200
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

        token_check = client.get("/token-check", headers=headers)
        assert token_check.status_code == 200
