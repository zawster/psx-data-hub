from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "mode,settings",
    [
        ("off", {"api_key_required": False, "expected_public_status": 200}),
        ("jwt", {"api_key_required": False, "expected_public_status": 401}),
        ("api_key", {"api_key_required": True, "api_keys": ["qa-key"], "expected_public_status": 401}),
        (
            "hybrid",
            {"api_key_required": False, "api_keys": ["qa-key"], "expected_public_status": 401},
        ),
    ],
    ids=["off", "jwt", "api_key", "hybrid"],
)
def test_compat_auth_modes(mode, settings, seeded_client_factory):
    api_mode = mode
    mode_settings = settings
    with seeded_client_factory(
        auth_mode=api_mode,
        api_key_required=mode_settings["api_key_required"],
        api_keys=mode_settings.get("api_keys"),
    ) as client:
        assert client.get("/status").status_code == mode_settings["expected_public_status"]
        assert client.get("/volume").status_code == mode_settings["expected_public_status"]
        assert client.get("/v1/market").status_code == mode_settings["expected_public_status"]

        if api_mode == "jwt":
            token = client.post("/token", data={"username": "demo", "password": "demo"})
            assert token.status_code == 200
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            assert client.get("/status", headers=headers).status_code == 200
            assert client.get("/volume", headers=headers).status_code == 200
            assert client.get("/v1/market", headers=headers).status_code == 200
            assert client.get("/token-check", headers=headers).status_code == 200
            assert client.get("/token-check").status_code == 401
            return

        if api_mode == "api_key":
            assert client.get("/status", headers={"X-API-Key": "qa-key"}).status_code == 200
            assert client.get("/volume", headers={"X-API-Key": "qa-key"}).status_code == 200
            assert client.get("/v1/market", headers={"X-API-Key": "qa-key"}).status_code == 200
            assert client.get("/token-check", headers={"X-API-Key": "qa-key"}).status_code == 401
            return

        if api_mode == "hybrid":
            token = client.post("/token", data={"username": "demo", "password": "demo"})
            assert token.status_code == 200
            token_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

            assert client.get("/status", headers={"X-API-Key": "qa-key"}).status_code == 200
            assert client.get("/volume", headers={"X-API-Key": "qa-key"}).status_code == 200
            assert client.get("/v1/market", headers={"X-API-Key": "qa-key"}).status_code == 200
            assert client.get("/status", headers=token_headers).status_code == 200
            assert client.get("/volume", headers=token_headers).status_code == 200
            assert client.get("/v1/market", headers=token_headers).status_code == 200
            assert client.get("/token-check", headers=token_headers).status_code == 200
