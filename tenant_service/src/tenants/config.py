"""Tenant service configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from common.db import build_database_url

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = str(_REPO_ROOT / ".env")


class TenantSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    AUTH0_DOMAIN: str
    AUTH0_CLIENT_ID: str

    DATABASE_URL: str | None = None
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_DB: str
    POSTGRES_SSLMODE: str | None = "require"
    SQLALCHEMY_POOL_SIZE: int = 1
    SQLALCHEMY_MAX_OVERFLOW: int = 0
    DB_ECHO_LOG: bool = False

    @property
    def database_url(self) -> str:
        return build_database_url(
            database_url=self.DATABASE_URL,
            postgres_user=self.POSTGRES_USER,
            postgres_password=self.POSTGRES_PASSWORD,
            postgres_host=self.POSTGRES_HOST,
            postgres_port=self.POSTGRES_PORT,
            postgres_db=self.POSTGRES_DB,
            postgres_sslmode=self.POSTGRES_SSLMODE,
        )


tenant_settings = TenantSettings()
