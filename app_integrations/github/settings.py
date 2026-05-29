"""GitHub App integration settings."""

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# app_integrations/github/settings.py → repo root is parents[2]
_ENV_FILE: str = str(Path(__file__).resolve().parents[2] / ".env")


class GitHubAppSettings(BaseSettings):
    """Settings for GitHub App installation and API access."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_APP_ID: int = 0
    GITHUB_APP_PRIVATE_KEY_PATH: str = ""
    GITHUB_APP_SLUG: str = ""
    GITHUB_INSTALL_STATE_SECRET: str = ""

    # Public base URL of the API server (GitHub App setup URL callback).
    SERVER_URL: str = "http://localhost:8000"

    # Where to send users after a successful install.
    WEBAPP_URL: str = "http://localhost:3000"

    @computed_field
    @property
    def github_app_private_key(self) -> str | None:
        if not self.GITHUB_APP_PRIVATE_KEY_PATH:
            return None
        path = Path(self.GITHUB_APP_PRIVATE_KEY_PATH)
        if not path.is_absolute():
            path = Path(_ENV_FILE).parent / path
        return path.read_text(encoding="utf-8") if path.exists() else None


github_settings = GitHubAppSettings()
