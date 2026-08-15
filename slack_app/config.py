"""Slack app configuration."""

from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the directory where this config file lives
SLACK_APP_DIR = Path(__file__).parent


class SlackSettings(BaseSettings):
    """Slack app settings."""

    model_config = SettingsConfigDict(
        env_file=(
            str(SLACK_APP_DIR / ".env"),
            str(SLACK_APP_DIR.parent / ".env"),
        ),
        case_sensitive=True,
        extra="ignore",
    )

    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    SLACK_APP_ID: str = ""
    SLACK_APP_CONFIG_TOKEN: str = ""
    SERVER_URL: str = "http://localhost:8000"
    INTEGRATIONS_PUBLIC_URL: str = ""
    LANGGRAPH_API_URL: str = "http://localhost:8000"

    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5433"
    POSTGRES_DB: str = "aegra"
    POSTGRES_SSLMODE: str | None = None
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


slack_settings = SlackSettings()
