"""Unit tests for Salesforce record-level Share mappers."""

from __future__ import annotations

import pytest

from integrations.salesforce.ingestion.record_access import (
    build_record_permission_edge,
    map_share_access_level,
    parent_id_field_for_sobject,
    share_object_name_for_sobject,
)


@pytest.mark.unit
def test_share_object_name_for_sobject() -> None:
    assert share_object_name_for_sobject("Account") == "AccountShare"
    assert share_object_name_for_sobject("Custom__c") == "Custom__Share"


@pytest.mark.unit
def test_map_share_access_level() -> None:
    assert map_share_access_level("Read") == "read"
    assert map_share_access_level("Edit") == "edit"
    assert map_share_access_level(None) == "read"


@pytest.mark.unit
def test_parent_id_field_for_sobject() -> None:
    assert parent_id_field_for_sobject("Account") == "AccountId"
    assert parent_id_field_for_sobject("Custom__c") == "ParentId"


@pytest.mark.unit
def test_build_record_permission_edge_for_user_share() -> None:
    edge = build_record_permission_edge(
        {
            "Id": "02c000000000001",
            "AccountId": "001000000000001AAA",
            "UserOrGroupId": "005000000000001AAA",
            "RowCause": "Rule",
            "AccountAccessLevel": "Read",
        },
        target_sobject="Account",
    )
    assert edge is not None
    assert edge["subject_kind"] == "identity"
    assert edge["subject_external_id"] == "005000000000001AAA"
    assert edge["resource_external_id"] == "Account"
    assert edge["extra"]["access_type"] == "record"
    assert edge["extra"]["record_id"] == "001000000000001AAA"
    assert edge["extra"]["row_cause"] == "Rule"


@pytest.mark.unit
def test_build_record_permission_edge_skips_unknown_row_cause() -> None:
    edge = build_record_permission_edge(
        {
            "ParentId": "001000000000001AAA",
            "UserOrGroupId": "005000000000001AAA",
            "RowCause": "InvalidCause",
            "AccessLevel": "Read",
        },
        target_sobject="Account",
    )
    assert edge is None
