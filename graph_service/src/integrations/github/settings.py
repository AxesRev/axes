from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GithubAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GITHUB_APP_ID: int
    GITHUB_APP_PRIVATE_KEY_PATH: str

    @computed_field
    @property
    def private_key(self) -> str:
        return Path(self.GITHUB_APP_PRIVATE_KEY_PATH).read_text(encoding="utf-8")


@lru_cache
def get_github_settings() -> GithubAppSettings:
    return GithubAppSettings()
