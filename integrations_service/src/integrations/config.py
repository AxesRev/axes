"""Integrations service configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.db import build_database_url

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = str(_REPO_ROOT / ".env")

DEFAULT_SALESFORCE_PACKAGE_VERSION_ID = "04tg50000008CgjAAE"
DEFAULT_SALESFORCE_LOGIN_URL = "https://login.salesforce.com"

SLACK_BOT_SCOPES = [
    "app_mentions:read",
    "channels:history",
    "chat:write",
    "commands",
    "im:write",
    "im:read",
    "im:history",
    "users:read",
    "users:read.email",
]


class IntegrationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5433"
    POSTGRES_DB: str = "aegra"
    POSTGRES_SSLMODE: str | None = "require"
    SQLALCHEMY_POOL_SIZE: int = 1
    SQLALCHEMY_MAX_OVERFLOW: int = 0
    DB_ECHO_LOG: bool = False

    SERVER_URL: str = ""
    WEBAPP_URL: str = "http://localhost:3000"

    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str

    GITHUB_APP_SLUG: str = ""
    INSTALL_SECRET: str
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str
    GITHUB_OAUTH_STATE_SECRET: str

    SALESFORCE_PACKAGE_VERSION_ID: str = DEFAULT_SALESFORCE_PACKAGE_VERSION_ID
    SALESFORCE_CLIENT_ID: str = ""
    SALESFORCE_PRIVATE_KEY: str | None = None
    SALESFORCE_PRIVATE_KEY_PATH: str | None = None
    SALESFORCE_LOGIN_URL: str = DEFAULT_SALESFORCE_LOGIN_URL

    @model_validator(mode="after")
    def _require_salesforce_private_key(self) -> Self:
        pem = (self.SALESFORCE_PRIVATE_KEY or "").strip()
        path = (self.SALESFORCE_PRIVATE_KEY_PATH or "").strip()
        if not pem and not path:
            raise ValueError("SALESFORCE_PRIVATE_KEY or SALESFORCE_PRIVATE_KEY_PATH is required")
        return self

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

    @property
    def salesforce_private_key(self) -> str:
        pem = (self.SALESFORCE_PRIVATE_KEY or "").strip()
        if pem:
            return pem.replace("\\n", "\n")
        if not self.SALESFORCE_PRIVATE_KEY_PATH:
            return ""
        path = Path(self.SALESFORCE_PRIVATE_KEY_PATH)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @property
    def jwt_domain(self) -> str:
        host = self.SALESFORCE_LOGIN_URL.removeprefix("https://").removeprefix("http://")
        if host.startswith("test."):
            return "test"
        if host.startswith("login."):
            return "login"
        return host.split(".")[0]

    @property
    def package_install_base_url(self) -> str:
        host = self.SALESFORCE_LOGIN_URL.removeprefix("https://").removeprefix("http://")
        return f"https://{host}/packaging/installPackage.apexp"


settings = IntegrationSettings()
