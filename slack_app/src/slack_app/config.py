"""Slack app configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from common.db import build_database_url

_APP_DIR = Path(__file__).resolve().parents[2]
_REPO_DIR = _APP_DIR.parent


class SlackSettings(BaseSettings):
    """Slack app settings."""

    model_config = SettingsConfigDict(
        env_file=(
            str(_APP_DIR / ".env"),
            str(_REPO_DIR / ".env"),
        ),
        case_sensitive=True,
        extra="ignore",
    )

    SLACK_SIGNING_SECRET: str
    SLACK_CLIENT_ID: str
    SLACK_CLIENT_SECRET: str
    SLACK_APP_ID: str = ""
    SLACK_APP_CONFIG_TOKEN: str | None = None
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SERVER_URL: str = "http://localhost:8000"
    INTEGRATIONS_PUBLIC_URL: str = ""
    LANGGRAPH_API_URL: str = "http://langraph-server.langraph-server.svc.cluster.local:8000"

    DATABASE_URL: str | None = None
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_DB: str
    POSTGRES_SSLMODE: str | None = "require"
    SQLALCHEMY_POOL_SIZE: int = 5
    SQLALCHEMY_MAX_OVERFLOW: int = 5
    DB_ECHO_LOG: bool = False

    @property
    def integrations_public_url(self) -> str:
        return (self.INTEGRATIONS_PUBLIC_URL or self.SERVER_URL).rstrip("/")

    @property
    def slack_oauth_redirect_uri(self) -> str:
        return f"{self.integrations_public_url}/app_integrations/slack/callback"

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


slack_settings = SlackSettings()
