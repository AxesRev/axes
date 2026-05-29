"""Ingest record ownership as AppIdentity -[:HAS_PERMISSION {permission: owner}]-> Resource."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    RecordPermissionEdgeRow,
    ResourceRow,
    merge_record_permissions,
    merge_resources,
)
from integrations.salesforce.models import PERMISSION_EFFECT_GRANT, PERMISSION_OWNER, build_owner_permission_extra
from integrations.salesforce.soql import build_account_by_name_soql, build_owned_records_soql

logger = logging.getLogger(__name__)

EXAMPLE_RESOURCE_NAME_PREFIX = "Axes Example Resource"


def resource_row_from_owned_record(
    record: dict[str, Any],
    *,
    sobject_type: str,
    connection: ConnectionRef,
) -> ResourceRow:
    record_id = str(record["Id"])
    name = str(record.get("Name") or record_id)
    return ResourceRow(
        external_id=record_id,
        name=name,
        uri=f"{sobject_type}/{record_id}",
        kind="record",
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


def owner_permission_edge_from_record(record: dict[str, Any]) -> RecordPermissionEdgeRow | None:
    owner_id = record.get("OwnerId")
    record_id = record.get("Id")
    if not owner_id or not record_id:
        return None
    record_id_str = str(record_id)
    return RecordPermissionEdgeRow(
        subject_kind="identity",
        subject_external_id=str(owner_id),
        subject_app=SALESFORCE_APP,
        resource_external_id=record_id_str,
        permission=PERMISSION_OWNER,
        effect=PERMISSION_EFFECT_GRANT,
        extra=build_owner_permission_extra(record_id=record_id_str),
    )


async def ingest_owned_records(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    sobject_type: str = "Account",
    name_prefix: str = EXAMPLE_RESOURCE_NAME_PREFIX,
) -> int:
    """Merge record Resources and owner HAS_PERMISSION edges for matching owned records."""
    records = query_all(
        sf,
        build_owned_records_soql(sobject_type=sobject_type, name_prefix=name_prefix),
    )
    resource_rows = [
        resource_row_from_owned_record(record, sobject_type=sobject_type, connection=connection) for record in records
    ]
    edge_rows: list[RecordPermissionEdgeRow] = []
    for record in records:
        edge = owner_permission_edge_from_record(record)
        if edge is not None:
            edge_rows.append(edge)

    await merge_resources(resource_rows)
    await merge_record_permissions(edge_rows)
    logger.info(
        "merged_owned_records sobject=%s resources=%s owner_edges=%s",
        sobject_type,
        len(resource_rows),
        len(edge_rows),
    )
    return len(edge_rows)


def seed_example_owned_accounts(
    sf: Salesforce,
    *,
    name_prefix: str = EXAMPLE_RESOURCE_NAME_PREFIX,
) -> list[str]:
    """Create one owned Account per active Standard user if missing. Returns created Account ids."""
    users = query_all(
        sf,
        "SELECT Id, Username FROM User WHERE IsActive = true AND UserType = 'Standard'",
    )
    created_ids: list[str] = []
    for user in users:
        user_id = str(user["Id"])
        username = str(user["Username"])
        account_name = f"{name_prefix} - {username}"
        existing = query_all(sf, build_account_by_name_soql(account_name=account_name))
        if existing:
            continue
        result = sf.Account.create({"Name": account_name, "OwnerId": user_id})
        created_ids.append(str(result["id"]))
        logger.info("seed_example_account owner=%s account_id=%s", username, result["id"])
    return created_ids
