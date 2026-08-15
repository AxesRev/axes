"""Independent SQLAlchemy engine for the shared RDS. Does not use aegra_api."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from slack_app.config import slack_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _ensure_engine() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is not None:
        return _session_maker

    _engine = create_async_engine(
        slack_settings.database_url,
        pool_size=slack_settings.SQLALCHEMY_POOL_SIZE,
        max_overflow=slack_settings.SQLALCHEMY_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=slack_settings.DB_ECHO_LOG,
    )
    _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_maker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with _ensure_engine()() as session:
        yield session
