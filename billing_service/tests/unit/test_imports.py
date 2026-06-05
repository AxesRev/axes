"""Smoke tests that core billing packages import after wheel layout changes."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_import_billing_service() -> None:
    from billing.service import sum_tokens_from_usage  # noqa: PLC0415

    assert sum_tokens_from_usage({}) == 0


@pytest.mark.unit
def test_import_billing_routes() -> None:
    from billing.routes import router  # noqa: PLC0415

    assert router.tags == ["billing"]
