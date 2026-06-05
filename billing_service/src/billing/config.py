"""Billing service configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = str(_REPO_ROOT / ".env")


class BillingSettings(BaseSettings):
    """Paddle billing settings (sandbox). Card data is never stored locally."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PADDLE_API_KEY: str = ""
    PADDLE_WEBHOOK_SECRET: str = ""
    PADDLE_USAGE_PRICE_ID: str = ""
    BILLING_TOKENS_PER_UNIT: int = 1000


billing_settings = BillingSettings()
