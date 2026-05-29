"""Slack app configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the directory where this config file lives
SLACK_APP_DIR = Path(__file__).parent


class SlackSettings(BaseSettings):
    """Slack app settings."""

    model_config = SettingsConfigDict(
        env_file=str(SLACK_APP_DIR / ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    SERVER_URL: str = "http://localhost:8000"
    LANGGRAPH_API_URL: str = "http://localhost:8000"

    @property
    def slack_oauth_redirect_uri(self) -> str:
        return f"{self.SERVER_URL.rstrip('/')}/slack/oauth/callback"


slack_settings = SlackSettings()
