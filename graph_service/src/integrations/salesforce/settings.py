from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from integrations.paths import ENV_FILE


class SalesforceAppSettings(BaseSettings):
    """JWT credentials for the Axes External Client App."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SALESFORCE_CLIENT_ID: str
    SALESFORCE_PRIVATE_KEY: str = Field(min_length=1)
    SALESFORCE_LOGIN_URL: str
    SALESFORCE_SHARE_OBJECTS: str = ""

    @field_validator("SALESFORCE_PRIVATE_KEY", mode="before")
    @classmethod
    def _normalize_pem(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().replace("\\n", "\n")
        return value

    @computed_field
    @property
    def private_key(self) -> str:
        return self.SALESFORCE_PRIVATE_KEY

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
