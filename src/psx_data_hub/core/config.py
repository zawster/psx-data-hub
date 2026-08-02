from __future__ import annotations

from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    market_watchlist: List[str] | str = Field(
        default_factory=lambda: ["PSO", "OGDC", "HBL", "ENGRO", "LUCKY"]
    )
    stale_threshold_seconds: int = 300
    quote_ttl_seconds: int = 45
    market_ttl_seconds: int = 45
    request_timeout_seconds: float = 12.0

    # Access control
    api_key_required: bool = False
    api_keys: List[str] | str = Field(default_factory=list)
    auth_mode: str = "off"
    legacy_users: List[str] | str = Field(default_factory=lambda: ["demo:demo:public"])
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10

    # Polling
    poll_interval_seconds: int = 30
    poll_symbols_per_tick: int = 10

    # Provider templates
    provider_base_url: str = "https://dps.psx.com.pk"
    provider_quote_url_template: str = "{provider_base_url}/company/{symbol}"
    provider_market_summary_url: str = "{provider_base_url}/market-summary"
    provider_timeseries_url_template: str = "{provider_base_url}/company/{symbol}/timeseries/{interval}"

    data_source_notice: str = "Data is delayed by at least 5 minutes."
    allowed_origins: List[str] | str = Field(default_factory=list)

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
            return [item.strip() for item in value.split(",") if item.strip()]
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
        "provider_timeseries_url_template",
    )
    @classmethod
    def _expand_provider_templates(cls, value: str, info: Any) -> str:
        data = getattr(info, "data", {}) or {}
        base_url = str(data.get("provider_base_url", "https://dps.psx.com.pk")).rstrip("/")
        expanded = value.replace("{provider_base_url}", base_url)
        expanded = expanded.replace("{PROVIDER_BASE_URL}", base_url)
        expanded = expanded.replace("{{provider_base_url}}", base_url)
        return expanded

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
