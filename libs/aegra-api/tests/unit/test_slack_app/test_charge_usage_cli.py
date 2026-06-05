"""Unit tests for the monthly billing cron CLI."""

from __future__ import annotations

import pytest
from slack_app import charge_usage


def test_validate_config_requires_paddle_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("slack_app.charge_usage.billing_settings.PADDLE_API_KEY", "")
    monkeypatch.setattr("slack_app.charge_usage.billing_settings.PADDLE_USAGE_PRICE_ID", "pri_test")
    assert charge_usage._validate_config() == "PADDLE_API_KEY is not configured"


def test_validate_config_requires_usage_price_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("slack_app.charge_usage.billing_settings.PADDLE_API_KEY", "test_sdbx_key")
    monkeypatch.setattr("slack_app.charge_usage.billing_settings.PADDLE_USAGE_PRICE_ID", "")
    assert charge_usage._validate_config() == "PADDLE_USAGE_PRICE_ID is not configured"


def test_validate_config_returns_none_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("slack_app.charge_usage.billing_settings.PADDLE_API_KEY", "test_sdbx_key")
    monkeypatch.setattr("slack_app.charge_usage.billing_settings.PADDLE_USAGE_PRICE_ID", "pri_test")
    assert charge_usage._validate_config() is None
