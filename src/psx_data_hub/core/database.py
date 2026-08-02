from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from psx_data_hub.core.config import settings
from psx_data_hub.storage.models import Base


def _ensure_db_path() -> None:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        return

    if url.database:
        db_path = Path(url.database)
        if str(db_path).startswith("~"):
            db_path = db_path.expanduser()
        db_path = db_path.expanduser()
        if db_path.suffix:
            db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_db_path()
engine = create_async_engine(settings.database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
