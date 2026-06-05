"""Ingest record ownership as AppIdentity -[:HAS_PERMISSION {permission: owner}]-> Resource."""

from __future__ import annotations

from typing import Any

from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    RecordPermissionEdgeRow,
    ResourceRow,
)
from integrations.salesforce.models import PERMISSION_EFFECT_GRANT, PERMISSION_OWNER, build_owner_permission_extra


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
