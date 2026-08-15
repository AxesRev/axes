"""Integrations service configuration."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

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
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5433"
    POSTGRES_DB: str = "aegra"
    POSTGRES_SSLMODE: str | None = None
    SQLALCHEMY_POOL_SIZE: int = 1
    SQLALCHEMY_MAX_OVERFLOW: int = 0
    DB_ECHO_LOG: bool = False

    SERVER_URL: str = ""
    WEBAPP_URL: str = "http://localhost:3000"

    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""

    GITHUB_APP_SLUG: str = ""
    GITHUB_INSTALL_STATE_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_OAUTH_STATE_SECRET: str = ""

    SALESFORCE_PACKAGE_VERSION_ID: str = DEFAULT_SALESFORCE_PACKAGE_VERSION_ID
    SALESFORCE_INSTALL_STATE_SECRET: str = ""
    SALESFORCE_CLIENT_ID: str = ""
    SALESFORCE_PRIVATE_KEY: str = ""
    SALESFORCE_PRIVATE_KEY_PATH: str = ""
    SALESFORCE_LOGIN_URL: str = DEFAULT_SALESFORCE_LOGIN_URL

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

    @property
    def install_state_secret(self) -> str:
        explicit = self.SALESFORCE_INSTALL_STATE_SECRET.strip()
        if explicit:
            return explicit
        return self.GITHUB_INSTALL_STATE_SECRET.strip()

    @property
    def salesforce_private_key(self) -> str:
        pem = self.SALESFORCE_PRIVATE_KEY.strip()
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
