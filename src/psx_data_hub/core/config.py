from __future__ import annotations

from typing import Any, List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "CHANGE_ME_IN_PRODUCTION"  # noqa: S105 — placeholder, rejected outside local


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    app_name: str = "psx-data-hub"
    env: str = "local"
    debug: bool = False
    api_prefix: str = "/v1"

    database_url: str = "sqlite+aiosqlite:///./data/psx-data-hub.db"

    # API behavior
    delay_minutes: int = 5
    market_watchlist: List[str] | str = Field(default_factory=list)
    stale_threshold_seconds: int = 300
    quote_ttl_seconds: int = 45
    market_ttl_seconds: int = 45
    request_timeout_seconds: float = 12.0

    # Access control
    api_key_required: bool = False
    api_keys: List[str] | str = Field(default_factory=list)
    auth_mode: str = "off"
    legacy_users: List[str] | str = Field(default_factory=lambda: ["demo:demo:public"])
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10

    # Rate-limit trust boundary. If the app is behind a proxy set this to the
    # proxy's IP(s); the limiter will then honor `X-Forwarded-For`.
    trusted_proxies: List[str] | str = Field(default_factory=list)
    rate_limit_max_buckets: int = 10_000

    # Polling
    poll_interval_seconds: int = 30
    poll_symbols_per_tick: int = 10

    # Provider templates. Verified against dps.psx.com.pk on 2026-08-03:
    #   /market-watch                    — HTML table, every listed quote
    #   /timeseries/int/{sym}            — intraday JSON
    #   /timeseries/eod/{sym}            — end-of-day JSON
    # The /company/{sym} page is a static profile with no live prices and is
    # no longer scraped for quotes.
    provider_base_url: str = "https://dps.psx.com.pk"
    provider_quote_url_template: str = "{provider_base_url}/company/{symbol}"
    provider_market_summary_url: str = "{provider_base_url}/market-watch"
    provider_indices_url: str = "{provider_base_url}/indices"
    provider_market_status_url: str = "{provider_base_url}/"
    provider_sector_summary_url: str = "{provider_base_url}/sector-summary"
    provider_timeseries_url_template: str = (
        "{provider_base_url}/timeseries/{interval}/{symbol}"
    )

    data_source_notice: str = "Data is delayed by at least 5 minutes."
    allowed_origins: List[str] | str = Field(default_factory=list)

    # Docs gating. Set to `False` in production to hide /docs and /redoc.
    docs_enabled: bool = True
    # Hide the `Server: uvicorn` header on responses.
    hide_server_header: bool = True

    @field_validator("market_watchlist", mode="before")
    @classmethod
    def _parse_watchlist(cls, value):
        if isinstance(value, str):
            return [item.upper() for item in _split_csv(value)]
        if not value:
            return []
        return [item.upper() for item in value]

    @field_validator("api_keys", mode="before")
    @classmethod
    def _parse_keys(cls, value):
        if isinstance(value, str):
            return _split_csv(value)
        return value or []

    @field_validator("legacy_users", mode="before")
    @classmethod
    def _parse_legacy_users(cls, value):
        if isinstance(value, str):
            return _split_csv(value)
        return value or []

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _parse_trusted_proxies(cls, value):
        if isinstance(value, str):
            return _split_csv(value)
        return value or []

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value):
        if isinstance(value, str):
            return _split_csv(value)
        return value or []

    @field_validator("auth_mode")
    @classmethod
    def _validate_auth_mode(cls, value):
        value = str(value or "off").strip().lower()
        valid = {"off", "api_key", "jwt", "hybrid"}
        if value not in valid:
            raise ValueError(f"auth_mode must be one of {sorted(valid)}")
        return value

    @field_validator(
        "provider_quote_url_template",
        "provider_market_summary_url",
        "provider_indices_url",
        "provider_market_status_url",
        "provider_sector_summary_url",
        "provider_timeseries_url_template",
    )
    @classmethod
    def _expand_provider_templates(cls, value: str, info: Any) -> str:
        data = getattr(info, "data", {}) or {}
        base_url = str(data.get("provider_base_url", "https://dps.psx.com.pk")).rstrip(
            "/"
        )
        expanded = value.replace("{provider_base_url}", base_url)
        expanded = expanded.replace("{PROVIDER_BASE_URL}", base_url)
        expanded = expanded.replace("{{provider_base_url}}", base_url)
        return expanded

    @model_validator(mode="after")
    def _validate_env_hardening(self):
        env = (self.env or "local").strip().lower()
        if env != "local":
            if self.jwt_secret_key == DEFAULT_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a non-default value "
                    f"when ENV={env!r}."
                )
            if self.debug:
                raise ValueError(f"DEBUG must be False when ENV={env!r}.")
            # Reject wildcard CORS in non-local envs.
            if isinstance(self.allowed_origins, list) and (
                not self.allowed_origins or "*" in self.allowed_origins
            ):
                raise ValueError(
                    "ALLOWED_ORIGINS must be an explicit list "
                    f"(no wildcard) when ENV={env!r}."
                )
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
