"""Smoke tests for tenant Lambda handler imports."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_import_tenant_http_handler() -> None:
    from tenants.app import handler

    assert callable(handler)
