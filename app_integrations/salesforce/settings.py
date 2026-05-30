"""Salesforce package install and JWT verification settings."""

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app_integrations.github.settings import github_settings
from app_integrations.salesforce.constants import (
    DEFAULT_SALESFORCE_LOGIN_URL,
    DEFAULT_SALESFORCE_PACKAGE_VERSION_ID,
    DEFAULT_SALESFORCE_PRIVATE_KEY_PATH,
)

_ENV_FILE: str = str(Path(__file__).resolve().parents[2] / ".env")


class SalesforceIntegrationSettings(BaseSettings):
    """Settings for AxesRev managed package install URLs and JWT API access."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SALESFORCE_PACKAGE_VERSION_ID: str = DEFAULT_SALESFORCE_PACKAGE_VERSION_ID
    SALESFORCE_INSTALL_STATE_SECRET: str = ""
    SALESFORCE_CLIENT_ID: str = ""
    SALESFORCE_PRIVATE_KEY_PATH: str = DEFAULT_SALESFORCE_PRIVATE_KEY_PATH
    SALESFORCE_LOGIN_URL: str = DEFAULT_SALESFORCE_LOGIN_URL

    SERVER_URL: str = "http://localhost:8000"
    WEBAPP_URL: str = "http://localhost:3000"

    @computed_field
    @property
    def install_state_secret(self) -> str:
        """Install JWT signing secret; falls back to GITHUB_INSTALL_STATE_SECRET."""
        explicit = self.SALESFORCE_INSTALL_STATE_SECRET.strip()
        if explicit:
            return explicit
        return github_settings.GITHUB_INSTALL_STATE_SECRET.strip()

    @computed_field
    @property
    def private_key(self) -> str | None:
        if not self.SALESFORCE_PRIVATE_KEY_PATH:
            return None
        path = Path(self.SALESFORCE_PRIVATE_KEY_PATH)
        if not path.is_absolute():
            path = Path(_ENV_FILE).parent / path
        return path.read_text(encoding="utf-8") if path.exists() else None

    @computed_field
    @property
    def jwt_domain(self) -> str:
        host = self.SALESFORCE_LOGIN_URL.removeprefix("https://").removeprefix("http://")
        if host.startswith("test."):
            return "test"
        if host.startswith("login."):
            return "login"
        return host.split(".")[0]

    @computed_field
    @property
    def package_install_base_url(self) -> str:
        host = self.SALESFORCE_LOGIN_URL.removeprefix("https://").removeprefix("http://")
        return f"https://{host}/packaging/installPackage.apexp"


salesforce_settings = SalesforceIntegrationSettings()
