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
    access_level_field_for_sobject,
    discover_share_pairs,
    normalize_share_access,
    normalize_share_access_level,
    parent_id_field_for_sobject,
    resolve_share_table_shape,
    share_object_for_sobject,
    sobject_for_share_object,
)
from integrations.salesforce.soql import build_share_table_soql


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
def test_access_level_field_for_sobject() -> None:
    assert access_level_field_for_sobject("Account") == "AccountAccessLevel"
    assert access_level_field_for_sobject("Asset") == "AssetAccessLevel"
    assert access_level_field_for_sobject("Campaign") == "CampaignAccessLevel"
    assert access_level_field_for_sobject("Custom__c") == "AccessLevel"


@pytest.mark.unit
def test_resolve_share_table_shape_uses_named_access_level() -> None:
    shape = resolve_share_table_shape(
        share_object_name="AssetShare",
        target_sobject="Asset",
        field_names={"Id", "AssetId", "UserOrGroupId", "RowCause", "AssetAccessLevel"},
    )
    assert shape is not None
    assert shape.parent_id_field == "AssetId"
    assert shape.access_level_field == "AssetAccessLevel"


@pytest.mark.unit
def test_resolve_share_table_shape_uses_parent_id_and_access_level() -> None:
    shape = resolve_share_table_shape(
        share_object_name="WorkStepTemplateShare",
        target_sobject="WorkStepTemplate",
        field_names={"Id", "ParentId", "UserOrGroupId", "RowCause", "AccessLevel"},
    )
    assert shape is not None
    assert shape.parent_id_field == "ParentId"
    assert shape.access_level_field == "AccessLevel"


@pytest.mark.unit
def test_resolve_share_table_shape_requires_user_or_group_and_row_cause() -> None:
    assert (
        resolve_share_table_shape(
            share_object_name="AssetShare",
            target_sobject="Asset",
            field_names={"Id", "AssetId", "AssetAccessLevel"},
        )
        is None
    )
    assert (
        resolve_share_table_shape(
            share_object_name="AssetShare",
            target_sobject="Asset",
            field_names={"Id", "AssetId", "UserOrGroupId", "AssetAccessLevel"},
        )
        is None
    )


@pytest.mark.unit
def test_build_share_table_soql_uses_described_fields() -> None:
    soql = build_share_table_soql(
        share_object_name="WorkStepTemplateShare",
        parent_id_field="ParentId",
        access_level_field="AccessLevel",
    )
    assert soql == ("SELECT Id, ParentId, UserOrGroupId, RowCause, AccessLevel FROM WorkStepTemplateShare")


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
def test_normalize_share_access_for_named_access_level_share_row() -> None:
    access = normalize_share_access(
        {
            "AssetId": "02i000000000001AAA",
            "UserOrGroupId": "005000000000001AAA",
            "RowCause": "Manual",
            "AssetAccessLevel": "Edit",
        },
        target_sobject="Asset",
        parent_id_field="AssetId",
        access_level_field="AssetAccessLevel",
    )
    assert access is not None
    assert access.record_id == "02i000000000001AAA"
    assert access.access_level == "edit"


@pytest.mark.unit
def test_normalize_share_access_for_parent_id_share_row() -> None:
    access = normalize_share_access(
        {
            "ParentId": "0ST000000000001AAA",
            "UserOrGroupId": "00G000000000001AAA",
            "RowCause": "Owner",
            "AccessLevel": "All",
        },
        target_sobject="WorkStepTemplate",
        parent_id_field="ParentId",
        access_level_field="AccessLevel",
    )
    assert access is not None
    assert access.record_id == "0ST000000000001AAA"
    assert access.subject.kind == "group"
    assert access.access_level == "all"


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
