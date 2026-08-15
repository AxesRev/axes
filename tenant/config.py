"""Tenant service configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = str(_REPO_ROOT / ".env")


class TenantSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    INTERNAL_API_SECRET: str = ""


tenant_settings = TenantSettings()
