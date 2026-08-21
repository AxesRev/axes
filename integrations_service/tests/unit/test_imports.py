"""Smoke tests for integrations Lambda handler imports."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_import_integrations_http_handler() -> None:
    from integrations.app import handler

    assert callable(handler)
