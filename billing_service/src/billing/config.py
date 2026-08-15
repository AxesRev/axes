"""Billing service configuration."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = str(_REPO_ROOT / ".env")


class BillingSettings(BaseSettings):
    """Paddle billing settings (sandbox). Card data is never stored locally."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PADDLE_API_KEY: str = ""
    PADDLE_WEBHOOK_SECRET: str = ""
    PADDLE_USAGE_PRICE_ID: str = ""
    BILLING_TOKENS_PER_UNIT: int = 1000
    INTERNAL_API_SECRET: str = ""

    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5433"
    POSTGRES_DB: str = "aegra"
    POSTGRES_SSLMODE: str | None = None
    SQLALCHEMY_POOL_SIZE: int = 1
    SQLALCHEMY_MAX_OVERFLOW: int = 0
    DB_ECHO_LOG: bool = False

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://") and "+asyncpg" not in url:
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        ssl = f"?ssl={self.POSTGRES_SSLMODE}" if self.POSTGRES_SSLMODE else ""
        return (
            f"postgresql+asyncpg://{quote_plus(self.POSTGRES_USER)}:{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}{ssl}"
        )


billing_settings = BillingSettings()
