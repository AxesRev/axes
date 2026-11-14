"""Salesforce SObject catalog → ResourceType nodes, plus instance Resource rows."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import describe_global, query_all
from integrations.salesforce.ingestion.shared import (
    ConnectionRef,
    ResourceRow,
    ResourceTypeRow,
    merge_resource_types,
    resource_type_external_id,
)

logger = logging.getLogger(__name__)

_OBJECT_PERM_SOQL = "SELECT SobjectType FROM ObjectPermissions"
_FIELD_PERM_SOQL = "SELECT SobjectType FROM FieldPermissions"


def catalog_sobject_types(
    summaries: list[dict[str, Any]],
    *,
    extra_sobject_types: set[str] | None = None,
) -> dict[str, str]:
    """Return SObject API name → display name for types to ingest.

    Queryable, non-setting, non-hidden objects from describeGlobal are included
    even when the org has no records. Object/field permission SObjectTypes are
    merged in so type-level grants always have a target.
    """
    types: dict[str, str] = {}
    for summary in summaries:
        name = summary.get("name")
        if not isinstance(name, str) or not name:
            continue
        if summary.get("customSetting") or summary.get("deprecatedAndHidden"):
            continue
        if not summary.get("queryable"):
            continue
        types[name] = name
    if extra_sobject_types:
        for extra in extra_sobject_types:
            if extra:
                types.setdefault(extra, extra)
    return types


def resource_type_row_from_sobject(
    sobject_type: str,
    *,
    connection: ConnectionRef,
) -> ResourceTypeRow:
    return ResourceTypeRow(
        external_id=resource_type_external_id(connection, sobject_type),
        name=sobject_type,
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


def resource_row_from_record(
    record_id: str,
    *,
    sobject_type: str,
    connection: ConnectionRef,
    name: str | None = None,
) -> ResourceRow:
    display_name = name or record_id
    return ResourceRow(
        external_id=record_id,
        name=display_name,
        uri=f"{sobject_type}/{record_id}",
        kind=sobject_type,
        resource_type_external_id=resource_type_external_id(connection, sobject_type),
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


def _permission_sobject_types(sf: Salesforce) -> set[str]:
    object_types = {str(row["SobjectType"]) for row in query_all(sf, _OBJECT_PERM_SOQL) if row.get("SobjectType")}
    field_types = {str(row["SobjectType"]) for row in query_all(sf, _FIELD_PERM_SOQL) if row.get("SobjectType")}
    return object_types | field_types


async def ingest_resource_types(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    extra_sobject_types: set[str] | None = None,
) -> dict[str, str]:
    extras = _permission_sobject_types(sf)
    if extra_sobject_types:
        extras |= extra_sobject_types
    catalog = catalog_sobject_types(describe_global(sf), extra_sobject_types=extras)
    rows = [resource_type_row_from_sobject(name, connection=connection) for name in sorted(catalog)]
    await merge_resource_types(rows)
    types_by_name = {row["name"]: row["external_id"] for row in rows}
    logger.info("merged_resource_types count=%s", len(rows))
    return types_by_name
