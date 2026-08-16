"""JWT Salesforce client for grant-execution REST calls."""

from __future__ import annotations

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_salesforce import Salesforce

_ENV_FILE = str(Path(__file__).resolve().parents[3] / ".env")


class SalesforceJwtSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SALESFORCE_CLIENT_ID: str
    SALESFORCE_PRIVATE_KEY_PATH: str
    SALESFORCE_LOGIN_URL: str

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


salesforce_settings = SalesforceJwtSettings()


def make_salesforce_client(*, username: str, settings: SalesforceJwtSettings | None = None) -> Salesforce:
    """Create a JWT-authenticated Salesforce REST client."""
    config = settings or salesforce_settings
    private_key = config.private_key
    if not config.SALESFORCE_CLIENT_ID or not private_key:
        raise ValueError("SALESFORCE_CLIENT_ID and SALESFORCE_PRIVATE_KEY_PATH are required")
    return Salesforce(
        consumer_key=config.SALESFORCE_CLIENT_ID,
        privatekey=private_key,
        username=username,
        domain=config.jwt_domain,
    )
