"""Unit tests for Salesforce ownership ingestion."""

from __future__ import annotations

import pytest

from integrations.salesforce.ingestion.ownership import (
    owner_permission_edge_from_record,
    resource_row_from_owned_record,
)
from integrations.salesforce.ingestion.shared import ConnectionRef
from integrations.salesforce.models import PERMISSION_OWNER


@pytest.mark.unit
def test_resource_row_from_owned_record() -> None:
    connection: ConnectionRef = {"app": "salesforce", "external_id": "00Dorg"}
    row = resource_row_from_owned_record(
        {"Id": "001000000000001AAA", "Name": "Axes Example Resource - user@example.com"},
        sobject_type="Account",
        connection=connection,
    )
    assert row["external_id"] == "001000000000001AAA"
    assert row["kind"] == "record"
    assert row["uri"] == "Account/001000000000001AAA"


@pytest.mark.unit
def test_owner_permission_edge_from_record() -> None:
    edge = owner_permission_edge_from_record(
        {
            "Id": "001000000000001AAA",
            "OwnerId": "005000000000001AAA",
            "Name": "Example",
        }
    )
    assert edge is not None
    assert edge["subject_kind"] == "identity"
    assert edge["subject_external_id"] == "005000000000001AAA"
    assert edge["resource_external_id"] == "001000000000001AAA"
    assert edge["permission"] == PERMISSION_OWNER
    assert edge["extra"]["row_cause"] == "Owner"
