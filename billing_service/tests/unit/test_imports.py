"""Smoke tests that core billing packages import after wheel layout changes."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_import_billing_service() -> None:
    from billing.service import sum_tokens_from_usage  # noqa: PLC0415

    assert sum_tokens_from_usage({}) == 0


@pytest.mark.unit
def test_import_billing_http_handler() -> None:
    from billing.app import handler  # noqa: PLC0415

    assert callable(handler)


@pytest.mark.unit
def test_import_charge_usage_handler() -> None:
    from billing.charge_usage import handler  # noqa: PLC0415

    assert callable(handler)
