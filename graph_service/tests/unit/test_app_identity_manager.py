"""Unit tests for AppIdentity manager hierarchy relationships."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_app_identity_manager_of_relationship() -> None:
    from nodes.app_identity import AppIdentity  # noqa: PLC0415

    assert AppIdentity.direct_reports.definition["relation_type"] == "MANAGER_OF"
    assert AppIdentity.manager.definition["relation_type"] == "MANAGER_OF"


@pytest.mark.unit
def test_app_identity_has_at_most_one_manager() -> None:
    from neomodel import AsyncOne  # noqa: PLC0415

    from nodes.app_identity import AppIdentity  # noqa: PLC0415

    assert AppIdentity.manager.manager is AsyncOne
