"""Unit tests for tenant billing helpers."""

from __future__ import annotations

import pytest
from slack_app.billing_service import _usage_quantity, sum_tokens_from_usage


def test_sum_tokens_from_usage_returns_zero_for_empty() -> None:
    assert sum_tokens_from_usage(None) == 0
    assert sum_tokens_from_usage({}) == 0


def test_sum_tokens_from_usage_sums_model_totals() -> None:
    usage = {
        "gpt-4o": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        "gpt-4o-mini": {"total_tokens": 25},
    }
    assert sum_tokens_from_usage(usage) == 175


def test_usage_quantity_returns_zero_for_no_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("slack_app.billing_service.billing_settings.BILLING_TOKENS_PER_UNIT", 1000)
    assert _usage_quantity(0) == 0


def test_usage_quantity_rounds_up_to_units(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("slack_app.billing_service.billing_settings.BILLING_TOKENS_PER_UNIT", 1000)
    assert _usage_quantity(1) == 1
    assert _usage_quantity(1000) == 1
    assert _usage_quantity(1001) == 2
