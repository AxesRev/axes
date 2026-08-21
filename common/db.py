"""Shared async SQLAlchemy engine for the shared RDS. Does not use aegra_api."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_database_url(
    *,
    database_url: str | None = None,
    postgres_user: str,
    postgres_password: str,
    postgres_host: str,
    postgres_port: str | int,
    postgres_db: str,
    postgres_sslmode: str | None = None,
) -> str:
    if database_url:
        url = database_url
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    ssl = f"?ssl={postgres_sslmode}" if postgres_sslmode else ""
    return (
        f"postgresql+asyncpg://{quote_plus(postgres_user)}:{quote_plus(postgres_password)}"
        f"@{postgres_host}:{postgres_port}/{postgres_db}{ssl}"
    )


class Database:
    def __init__(
        self,
        url: str,
        *,
        pool_size: int = 1,
        max_overflow: int = 0,
        echo: bool = False,
    ) -> None:
        self._url = url
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._echo = echo
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_engine(self) -> async_sessionmaker[AsyncSession]:
        loop = asyncio.get_running_loop()
        if self._session_maker is not None and self._loop is loop:
            return self._session_maker
        self._engine = create_async_engine(
            self._url,
            pool_size=self._pool_size,
            max_overflow=self._max_overflow,
            pool_pre_ping=True,
            echo=self._echo,
        )
        self._session_maker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._loop = loop
        return self._session_maker

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        async with self._ensure_engine()() as session:
            yield session

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_maker = None
        self._loop = None
