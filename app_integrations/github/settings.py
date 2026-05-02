"""GitHub OAuth integration settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubOAuthSettings(BaseSettings):
    """Settings for GitHub OAuth identity linking."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # Secret key used to HMAC-sign the OAuth `state` parameter sent to GitHub.
    # Must be a long random string (e.g. `openssl rand -hex 32`).
    GITHUB_OAUTH_STATE_SECRET: str = ""

    # Public base URL of this server (used to build redirect / connect URLs).
    SERVER_URL: str = "http://localhost:8000"


github_settings = GitHubOAuthSettings()
