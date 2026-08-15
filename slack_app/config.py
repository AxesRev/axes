"""Slack app configuration."""

from pathlib import Path

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

    @property
    def integrations_public_url(self) -> str:
        return (self.INTEGRATIONS_PUBLIC_URL or self.SERVER_URL).rstrip("/")

    @property
    def slack_oauth_redirect_uri(self) -> str:
        return f"{self.integrations_public_url}/app_integrations/slack/callback"


slack_settings = SlackSettings()
