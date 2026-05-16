"""Smoke tests that core packages import after wheel layout changes."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_import_nodes_tenant() -> None:
    from nodes.tenant import Tenant  # noqa: PLC0415

    assert Tenant.__name__ == "Tenant"


@pytest.mark.unit
def test_import_nodes_package_registers_exports() -> None:
    import nodes  # noqa: PLC0415

    assert nodes.Tenant.__name__ == "Tenant"
