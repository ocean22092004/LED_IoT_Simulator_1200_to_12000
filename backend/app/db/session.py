import asyncio
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config import get_settings

DATABASE_READY_TIMEOUT_SECONDS = 1.5


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url,
        connect_args={"timeout": DATABASE_READY_TIMEOUT_SECONDS},
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def database_is_ready() -> bool:
    try:
        async with asyncio.timeout(DATABASE_READY_TIMEOUT_SECONDS):
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError):
        return False
    return True
