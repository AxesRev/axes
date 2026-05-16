"""GitHub OAuth integration settings."""

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# app_integrations/github/settings.py → repo root is parents[2]
_ENV_FILE: str = str(Path(__file__).resolve().parents[2] / ".env")


class GitHubOAuthSettings(BaseSettings):
    """Settings for GitHub OAuth identity linking."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # Secret key used to HMAC-sign the OAuth `state` parameter sent to GitHub.
    GITHUB_OAUTH_STATE_SECRET: str = ""

    # Public base URL of this server (used to build redirect / connect URLs).
    SERVER_URL: str = "http://localhost:8000"

    # GitHub App credentials (used to authenticate as the app via JWT).
    GITHUB_APP_ID: int = 0
    GITHUB_APP_PRIVATE_KEY_PATH: str = ""

    @computed_field
    @property
    def github_app_private_key(self) -> str | None:
        if not self.GITHUB_APP_PRIVATE_KEY_PATH:
            return None
        path = Path(self.GITHUB_APP_PRIVATE_KEY_PATH)
        if not path.is_absolute():
            path = Path(_ENV_FILE).parent / path
        return path.read_text(encoding="utf-8") if path.exists() else None


github_settings = GitHubOAuthSettings()
