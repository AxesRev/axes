"""Salesforce SObject resource ingestion → Resource nodes."""

from __future__ import annotations

import logging

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.shared import (
    ConnectionRef,
    ResourceRow,
    merge_resources,
)

logger = logging.getLogger(__name__)

_OBJECT_PERM_SOQL = "SELECT SobjectType FROM ObjectPermissions"
_FIELD_PERM_SOQL = "SELECT SobjectType FROM FieldPermissions"


def resource_row_from_sobject(
    sobject_type: str,
    *,
    connection: ConnectionRef,
) -> ResourceRow:
    return ResourceRow(
        external_id=sobject_type,
        name=sobject_type,
        uri=sobject_type,
        kind="object",
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


async def ingest_resources(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    extra_sobject_types: set[str] | None = None,
) -> dict[str, str]:
    object_types = {str(row["SobjectType"]) for row in query_all(sf, _OBJECT_PERM_SOQL) if row.get("SobjectType")}
    field_types = {str(row["SobjectType"]) for row in query_all(sf, _FIELD_PERM_SOQL) if row.get("SobjectType")}
    sobject_types = object_types | field_types
    if extra_sobject_types:
        sobject_types |= extra_sobject_types
    rows = [resource_row_from_sobject(name, connection=connection) for name in sorted(sobject_types)]
    await merge_resources(rows)
    resources_by_name = {row["external_id"]: row["external_id"] for row in rows}
    logger.info("merged_resources count=%s", len(rows))
    return resources_by_name
