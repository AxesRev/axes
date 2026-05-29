"""Unit tests for Salesforce ID and Share normalization."""

from __future__ import annotations

import pytest

from integrations.salesforce.ids import (
    GraphSubjectRef,
    graph_subject_from_user_or_group_id,
    validate_salesforce_id,
)
from integrations.salesforce.ingestion.record_access import record_permission_edge_from_share_access
from integrations.salesforce.share_objects import (
    discover_share_pairs,
    normalize_share_access,
    normalize_share_access_level,
    parent_id_field_for_sobject,
    share_object_for_sobject,
    sobject_for_share_object,
)


@pytest.mark.unit
def test_validate_salesforce_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        validate_salesforce_id("bad")
    assert validate_salesforce_id("005000000000001AAA") == "005000000000001AAA"


@pytest.mark.unit
def test_graph_subject_from_user_or_group_id() -> None:
    assert graph_subject_from_user_or_group_id("005000000000001AAA") == GraphSubjectRef(
        kind="identity",
        external_id="005000000000001AAA",
    )
    assert graph_subject_from_user_or_group_id("00G000000000001AAA") == GraphSubjectRef(
        kind="group",
        external_id="00G000000000001AAA",
    )
    assert graph_subject_from_user_or_group_id("001000000000001AAA") is None
    assert graph_subject_from_user_or_group_id("not-an-id") is None


@pytest.mark.unit
def test_share_object_name_round_trip() -> None:
    assert share_object_for_sobject("Account") == "AccountShare"
    assert share_object_for_sobject("Custom__c") == "Custom__Share"
    assert sobject_for_share_object("AccountShare") == "Account"
    assert sobject_for_share_object("Custom__Share") == "Custom__c"
    assert sobject_for_share_object("NotAShareObject") is None


@pytest.mark.unit
def test_normalize_share_access_level() -> None:
    assert normalize_share_access_level("Read") == "read"
    assert normalize_share_access_level("Edit") == "edit"
    assert normalize_share_access_level(None) == "read"


@pytest.mark.unit
def test_parent_id_field_for_sobject() -> None:
    assert parent_id_field_for_sobject("Account") == "AccountId"
    assert parent_id_field_for_sobject("Custom__c") == "ParentId"


@pytest.mark.unit
def test_normalize_share_access_for_account_share_row() -> None:
    access = normalize_share_access(
        {
            "AccountId": "001000000000001AAA",
            "UserOrGroupId": "005000000000001AAA",
            "RowCause": "Rule",
            "AccountAccessLevel": "Read",
        },
        target_sobject="Account",
    )
    assert access is not None
    assert access.record_id == "001000000000001AAA"
    assert access.subject.kind == "identity"
    assert access.subject.external_id == "005000000000001AAA"
    assert access.row_cause == "Rule"
    assert access.access_level == "read"


@pytest.mark.unit
def test_normalize_share_access_skips_unknown_row_cause() -> None:
    assert (
        normalize_share_access(
            {
                "AccountId": "001000000000001AAA",
                "UserOrGroupId": "005000000000001AAA",
                "RowCause": "InvalidCause",
                "AccountAccessLevel": "Read",
            },
            target_sobject="Account",
        )
        is None
    )


@pytest.mark.unit
def test_record_permission_edge_from_share_access() -> None:
    access = normalize_share_access(
        {
            "AccountId": "001000000000001AAA",
            "UserOrGroupId": "005000000000001AAA",
            "RowCause": "Rule",
            "AccountAccessLevel": "Read",
        },
        target_sobject="Account",
    )
    assert access is not None
    edge = record_permission_edge_from_share_access(access, target_sobject="Account")
    assert edge["subject_kind"] == "identity"
    assert edge["resource_external_id"] == "Account"
    assert edge["extra"]["access_type"] == "record"
    assert edge["extra"]["record_id"] == "001000000000001AAA"


@pytest.mark.unit
def test_discover_share_pairs_uses_allowlist_without_describe() -> None:
    class FakeSf:
        def describe(self) -> dict[str, list[object]]:
            raise AssertionError("describe should not be called when allowlist is set")

    pairs = discover_share_pairs(FakeSf(), allowlist=frozenset({"AccountShare", "BadName"}))  # type: ignore[arg-type]
    assert pairs == [("AccountShare", "Account")]
