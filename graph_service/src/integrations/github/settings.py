from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = str(_REPO_ROOT / ".env")


class GithubAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_APP_ID: int
    GITHUB_APP_PRIVATE_KEY_PATH: str

    @computed_field
    @property
    def private_key(self) -> str:
        path = Path(self.GITHUB_APP_PRIVATE_KEY_PATH)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path.read_text(encoding="utf-8")


class RunnerSettings(BaseSettings):
    """Settings required to run the fetcher as a standalone script."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"

    # Postgres
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_DB: str = "aegra"

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
