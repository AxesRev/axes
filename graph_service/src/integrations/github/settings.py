from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from integrations.paths import ENV_FILE


class GithubAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_APP_ID: int
    GITHUB_APP_PRIVATE_KEY: str = Field(min_length=1)

    @field_validator("GITHUB_APP_PRIVATE_KEY", mode="before")
    @classmethod
    def _normalize_pem(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().replace("\\n", "\n")
        return value

    @computed_field
    @property
    def private_key(self) -> str:
        return self.GITHUB_APP_PRIVATE_KEY


class RunnerSettings(BaseSettings):
    """Settings required to run the fetcher as a standalone script."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str

    @computed_field
    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def neomodel_url(self) -> str:
        uri = self.NEO4J_URI.removeprefix("bolt://")
        return f"bolt://{self.NEO4J_USER}:{self.NEO4J_PASSWORD}@{uri}"


@lru_cache
def get_github_settings() -> GithubAppSettings:
    return GithubAppSettings()


@lru_cache
def get_runner_settings() -> RunnerSettings:
    return RunnerSettings()
