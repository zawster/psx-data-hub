from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from psx_data_hub.api.middleware import HideServerHeaderMiddleware, RateLimitMiddleware
from psx_data_hub.api.routes import compat, health, indices, market, stocks
from psx_data_hub.core.config import settings
from psx_data_hub.core.database import AsyncSessionLocal, init_db
from psx_data_hub.storage.repo import DataRepository

log = logging.getLogger("psx_data_hub.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = DataRepository(session)
        for symbol in settings.market_watchlist:
            await repo.upsert_symbol(symbol)
    yield


def _cors_origins() -> list[str]:
    """Resolve the CORS origin list.

    In `local` env with no explicit config we still permit `*` for developer
    convenience. Everywhere else the config validator has already rejected a
    wildcard, so we return the explicit allowlist as-is.
    """
    if settings.allowed_origins:
        return list(settings.allowed_origins)
    if settings.env == "local":
        return ["*"]
    return []


def create_app() -> FastAPI:
    docs_url = "/docs" if settings.docs_enabled else None
    redoc_url = "/redoc" if settings.docs_enabled else None
    openapi_url = "/openapi.json" if settings.docs_enabled else None

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    if settings.hide_server_header:
        app.add_middleware(HideServerHeaderMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_per_minute,
        requests_burst=settings.rate_limit_burst,
        max_buckets=settings.rate_limit_max_buckets,
        trusted_proxies=settings.trusted_proxies,
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(market.router, prefix=settings.api_prefix)
    app.include_router(stocks.router, prefix=f"{settings.api_prefix}/stocks")
    app.include_router(indices.router, prefix=f"{settings.api_prefix}/indices")
    app.include_router(compat.router)
    return app


app = create_app()
