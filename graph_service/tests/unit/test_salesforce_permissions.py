"""Unit tests for Salesforce type-level permission mappers."""

from __future__ import annotations

import pytest

from integrations.salesforce.ingestion.permissions import (
    build_field_permission_edges,
    build_object_permission_edges,
    permission_effect,
)
from integrations.salesforce.models import (
    PERMISSION_EDIT,
    PERMISSION_EFFECT_GRANT,
    PERMISSION_EFFECT_MUTE,
    PERMISSION_READ,
    PERMISSION_VIEW_ALL,
)


@pytest.mark.unit
def test_build_object_permission_edges_maps_enabled_flags() -> None:
    edges = build_object_permission_edges(
        {
            "ParentId": "0PS1",
            "SobjectType": "Account",
            "PermissionsRead": True,
            "PermissionsCreate": False,
            "PermissionsEdit": True,
            "PermissionsDelete": False,
            "PermissionsViewAllRecords": True,
            "PermissionsModifyAllRecords": False,
        },
        muting_profile_ids=set(),
    )
    permissions = {edge["permission"] for edge in edges}
    assert permissions == {PERMISSION_READ, PERMISSION_EDIT, PERMISSION_VIEW_ALL}
    assert all(edge["effect"] == PERMISSION_EFFECT_GRANT for edge in edges)
    assert all(edge["extra"]["access_type"] == "object" for edge in edges)


@pytest.mark.unit
def test_build_object_permission_edges_uses_mute_effect_for_muting_profiles() -> None:
    edges = build_object_permission_edges(
        {
            "ParentId": "0PSMUTE",
            "SobjectType": "Account",
            "PermissionsRead": True,
            "PermissionsCreate": False,
            "PermissionsEdit": False,
            "PermissionsDelete": False,
            "PermissionsViewAllRecords": False,
            "PermissionsModifyAllRecords": False,
        },
        muting_profile_ids={"0PSMUTE"},
    )
    assert len(edges) == 1
    assert edges[0]["effect"] == PERMISSION_EFFECT_MUTE


@pytest.mark.unit
def test_build_field_permission_edges_groups_fields_by_permission() -> None:
    edges = build_field_permission_edges(
        [
            {
                "ParentId": "0PS1",
                "SobjectType": "Account",
                "Field": "Account.AnnualRevenue",
                "PermissionsRead": True,
                "PermissionsEdit": False,
            },
            {
                "ParentId": "0PS1",
                "SobjectType": "Account",
                "Field": "Account.Name",
                "PermissionsRead": True,
                "PermissionsEdit": True,
            },
        ],
        muting_profile_ids=set(),
    )
    assert len(edges) == 2
    read_edge = next(edge for edge in edges if edge["permission"] == PERMISSION_READ)
    edit_edge = next(edge for edge in edges if edge["permission"] == PERMISSION_EDIT)
    assert read_edge["extra"]["fields"] == ["Account.AnnualRevenue", "Account.Name"]
    assert edit_edge["extra"]["fields"] == ["Account.Name"]


@pytest.mark.unit
def test_permission_effect_returns_grant_by_default() -> None:
    assert permission_effect("0PS1", set()) == PERMISSION_EFFECT_GRANT
