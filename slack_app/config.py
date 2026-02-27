"""Slack app configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackSettings(BaseSettings):
    """Slack app settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""


slack_settings = SlackSettings()
