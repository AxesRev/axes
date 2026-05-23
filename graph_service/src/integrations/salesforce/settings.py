from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = str(_REPO_ROOT / ".env")


class SalesforceAppSettings(BaseSettings):
    """JWT credentials for the Axes External Client App."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SALESFORCE_CLIENT_ID: str
    SALESFORCE_PRIVATE_KEY_PATH: str
    SALESFORCE_LOGIN_URL: str = "https://login.salesforce.com"
    SALESFORCE_USERNAME: str = ""
    SALESFORCE_ORG_ID: str = ""
    SALESFORCE_SHARE_OBJECTS: str = ""

    @computed_field
    @property
    def private_key(self) -> str:
        path = Path(self.SALESFORCE_PRIVATE_KEY_PATH)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path.read_text(encoding="utf-8")

    @computed_field
    @property
    def jwt_domain(self) -> str:
        """Domain argument for simple-salesforce JWT login."""
        host = self.SALESFORCE_LOGIN_URL.removeprefix("https://").removeprefix("http://")
        if host.startswith("test."):
            return "test"
        if host.startswith("login."):
            return "login"
        return host.split(".")[0]

    @computed_field
    @property
    def share_object_allowlist(self) -> frozenset[str]:
        raw = self.SALESFORCE_SHARE_OBJECTS.strip()
        if not raw:
            return frozenset()
        return frozenset(part.strip() for part in raw.split(",") if part.strip())


@lru_cache
def get_salesforce_settings() -> SalesforceAppSettings:
    return SalesforceAppSettings()
