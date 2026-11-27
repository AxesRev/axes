from __future__ import annotations

from types import SimpleNamespace

import pytest

from integrations.github.ingestion.repos import resource_row_from_github
from integrations.github.ingestion.scopes import scope_rows_for_connection
from integrations.github.ingestion.shared import ConnectionRef as GithubConnectionRef
from integrations.github.ingestion.shared import scope_external_id as github_type_id
from integrations.salesforce.ids import GraphSubjectRef
from integrations.salesforce.ingestion.ownership import resource_row_from_owned_record
from integrations.salesforce.ingestion.permissions import (
    build_field_permission_edges,
    build_object_permission_edges,
)
from integrations.salesforce.ingestion.record_access import record_permission_edge_from_share_access
from integrations.salesforce.ingestion.resources import (
    catalog_sobject_types,
    resource_row_from_record,
    scope_row_from_sobject,
)
from integrations.salesforce.ingestion.shared import ConnectionRef as SalesforceConnectionRef
from integrations.salesforce.ingestion.shared import scope_external_id as salesforce_type_id
from integrations.salesforce.share_objects import NormalizedShareAccess


@pytest.mark.unit
def test_salesforce_catalog_includes_types_without_instances() -> None:
    catalog = catalog_sobject_types(
        [
            {"name": "Campaign", "queryable": True},
            {"name": "EmptyCustom__c", "queryable": True, "custom": True},
            {"name": "Setting__c", "queryable": True, "customSetting": True},
            {"name": "OldThing", "queryable": True, "deprecatedAndHidden": True},
            {"name": "NotQueryable", "queryable": False},
        ],
        extra_sobject_types={"NotQueryable"},
    )

    assert "Campaign" in catalog
    assert "EmptyCustom__c" in catalog
    assert "Setting__c" not in catalog
    assert "OldThing" not in catalog
    assert "NotQueryable" in catalog


@pytest.mark.unit
def test_salesforce_scope_ids_are_connection_scoped() -> None:
    first: SalesforceConnectionRef = {"app": "salesforce", "external_id": "00Daaa"}
    second: SalesforceConnectionRef = {"app": "salesforce", "external_id": "00Dbbb"}
    row = scope_row_from_sobject("Campaign", connection=first)

    assert row["name"] == "Campaign"
    assert row["external_id"] == salesforce_type_id(first, "Campaign")
    assert row["external_id"] != salesforce_type_id(second, "Campaign")


@pytest.mark.unit
def test_salesforce_object_permissions_target_scope() -> None:
    type_id = "salesforce:00Daaa:Campaign"
    edges = build_object_permission_edges(
        {
            "ParentId": "0PSaaa",
            "SobjectType": "Campaign",
            "PermissionsRead": True,
            "PermissionsCreate": True,
            "PermissionsEdit": False,
            "PermissionsDelete": False,
            "PermissionsViewAllRecords": False,
            "PermissionsModifyAllRecords": False,
        },
        scope_external_id=type_id,
        muting_profile_ids=set(),
    )

    assert {edge["permission"] for edge in edges} == {"read", "create"}
    assert all(edge["resource_external_id"] == type_id for edge in edges)


@pytest.mark.unit
def test_salesforce_field_permissions_target_scope() -> None:
    type_id = "salesforce:00Daaa:Campaign"
    edges = build_field_permission_edges(
        [
            {
                "ParentId": "0PSaaa",
                "SobjectType": "Campaign",
                "Field": "Campaign.Name",
                "PermissionsRead": True,
                "PermissionsEdit": False,
            }
        ],
        scopes_by_name={"Campaign": type_id},
        muting_profile_ids=set(),
    )

    assert len(edges) == 1
    assert edges[0]["resource_external_id"] == type_id
    assert edges[0]["permission"] == "read"


@pytest.mark.unit
def test_salesforce_record_share_creates_instance_of_type() -> None:
    connection: SalesforceConnectionRef = {"app": "salesforce", "external_id": "00Daaa"}
    record_id = "701000000000001AAA"
    resource = resource_row_from_record(record_id, sobject_type="Campaign", connection=connection)
    edge = record_permission_edge_from_share_access(
        NormalizedShareAccess(
            record_id=record_id,
            subject=GraphSubjectRef(kind="identity", external_id="005000000000001AAA"),
            row_cause="Manual",
            access_level="edit",
        )
    )

    assert resource["external_id"] == record_id
    assert resource["kind"] == "Campaign"
    assert resource["scope_external_id"] == salesforce_type_id(connection, "Campaign")
    assert edge["resource_external_id"] == record_id
    assert edge["resource_external_id"] != resource["scope_external_id"]


@pytest.mark.unit
def test_owned_record_is_instance_of_sobject_type() -> None:
    connection: SalesforceConnectionRef = {"app": "salesforce", "external_id": "00Daaa"}
    resource = resource_row_from_owned_record(
        {"Id": "701000000000002AAA", "Name": "Q1 Push", "OwnerId": "005000000000001AAA"},
        sobject_type="Campaign",
        connection=connection,
    )

    assert resource["name"] == "Q1 Push"
    assert resource["kind"] == "Campaign"
    assert resource["scope_external_id"] == salesforce_type_id(connection, "Campaign")


@pytest.mark.unit
def test_github_repo_instances_point_at_catalog_type() -> None:
    connection: GithubConnectionRef = {"app": "github", "external_id": "42"}
    type_rows = scope_rows_for_connection(connection)
    repo = SimpleNamespace(id=99, name="axes", full_name="acme/axes")
    resource = resource_row_from_github(repo, connection=connection)

    assert type_rows
    assert resource["scope_external_id"] in {row["external_id"] for row in type_rows}
    assert resource["scope_external_id"] == github_type_id(connection, resource["kind"])
    assert all(row["connection_external_id"] == "42" for row in type_rows)
