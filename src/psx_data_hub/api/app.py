from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from psx_data_hub.api.middleware import RateLimitMiddleware
from psx_data_hub.api.routes import compat, health, indices, market, stocks
from psx_data_hub.core.config import settings
from psx_data_hub.core.database import init_db
from psx_data_hub.storage.repo import DataRepository
from psx_data_hub.core.database import AsyncSessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = DataRepository(session)
        for symbol in settings.market_watchlist:
            await repo.upsert_symbol(symbol)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_per_minute,
        requests_burst=settings.rate_limit_burst,
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(market.router, prefix=settings.api_prefix)
    app.include_router(stocks.router, prefix=f"{settings.api_prefix}/stocks")
    app.include_router(indices.router, prefix=f"{settings.api_prefix}/indices")
    app.include_router(compat.router)
    return app


app = create_app()
