"""Salesforce type-level permissions → Profile HAS_PERMISSION edges."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all, query_muting_permission_set_links
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    ProfilePermissionEdgeRow,
    merge_profile_permissions,
)
from integrations.salesforce.models import (
    PERMISSION_CREATE,
    PERMISSION_DELETE,
    PERMISSION_EDIT,
    PERMISSION_EFFECT_GRANT,
    PERMISSION_EFFECT_MUTE,
    PERMISSION_MODIFY_ALL,
    PERMISSION_READ,
    PERMISSION_VIEW_ALL,
    build_field_permission_extra,
    build_object_permission_extra,
)

logger = logging.getLogger(__name__)

_OBJECT_PERM_SOQL = """
SELECT ParentId, SobjectType,
       PermissionsRead, PermissionsCreate, PermissionsEdit, PermissionsDelete,
       PermissionsViewAllRecords, PermissionsModifyAllRecords
FROM ObjectPermissions
"""

_FIELD_PERM_SOQL = """
SELECT ParentId, SobjectType, Field, PermissionsRead, PermissionsEdit
FROM FieldPermissions
"""

_OBJECT_FLAG_MAP: tuple[tuple[str, str], ...] = (
    ("PermissionsRead", PERMISSION_READ),
    ("PermissionsCreate", PERMISSION_CREATE),
    ("PermissionsEdit", PERMISSION_EDIT),
    ("PermissionsDelete", PERMISSION_DELETE),
    ("PermissionsViewAllRecords", PERMISSION_VIEW_ALL),
    ("PermissionsModifyAllRecords", PERMISSION_MODIFY_ALL),
)


def is_muting_profile(profile_id: str, muting_profile_ids: set[str]) -> bool:
    return profile_id in muting_profile_ids


def permission_effect(profile_id: str, muting_profile_ids: set[str]) -> str:
    if is_muting_profile(profile_id, muting_profile_ids):
        return PERMISSION_EFFECT_MUTE
    return PERMISSION_EFFECT_GRANT


def build_object_permission_edges(
    record: dict[str, Any],
    *,
    muting_profile_ids: set[str],
) -> list[ProfilePermissionEdgeRow]:
    profile_id = str(record["ParentId"])
    sobject_type = str(record["SobjectType"])
    effect = permission_effect(profile_id, muting_profile_ids)
    extra = build_object_permission_extra()
    edges: list[ProfilePermissionEdgeRow] = []
    for field_name, permission_name in _OBJECT_FLAG_MAP:
        if record.get(field_name):
            edges.append(
                ProfilePermissionEdgeRow(
                    profile_external_id=profile_id,
                    profile_app=SALESFORCE_APP,
                    resource_external_id=sobject_type,
                    permission=permission_name,
                    effect=effect,
                    extra=extra,
                )
            )
    return edges


def build_field_permission_edges(
    records: list[dict[str, Any]],
    *,
    muting_profile_ids: set[str],
) -> list[ProfilePermissionEdgeRow]:
    grouped: dict[tuple[str, str, str, str], list[str]] = {}
    for record in records:
        profile_id = str(record["ParentId"])
        sobject_type = str(record["SobjectType"])
        field_name = str(record.get("Field") or "")
        if not field_name:
            continue
        if record.get("PermissionsRead"):
            key = (profile_id, sobject_type, PERMISSION_READ, permission_effect(profile_id, muting_profile_ids))
            grouped.setdefault(key, []).append(field_name)
        if record.get("PermissionsEdit"):
            key = (profile_id, sobject_type, PERMISSION_EDIT, permission_effect(profile_id, muting_profile_ids))
            grouped.setdefault(key, []).append(field_name)

    edges: list[ProfilePermissionEdgeRow] = []
    for (profile_id, sobject_type, permission_name, effect), fields in grouped.items():
        unique_fields = sorted(set(fields))
        edges.append(
            ProfilePermissionEdgeRow(
                profile_external_id=profile_id,
                profile_app=SALESFORCE_APP,
                resource_external_id=sobject_type,
                permission=permission_name,
                effect=effect,
                extra=build_field_permission_extra(*unique_fields),
            )
        )
    return edges


def fetch_muting_profile_ids(sf: Salesforce) -> set[str]:
    rows = query_muting_permission_set_links(sf)
    return {str(row["PermissionSetId"]) for row in rows}


async def ingest_permissions(
    sf: Salesforce,
    *,
    connection: ConnectionRef,  # noqa: ARG001
    resources_by_name: dict[str, str],
) -> None:
    muting_profile_ids = fetch_muting_profile_ids(sf)
    object_records = query_all(sf, _OBJECT_PERM_SOQL)
    field_records = query_all(sf, _FIELD_PERM_SOQL)
    edges: list[ProfilePermissionEdgeRow] = []
    for record in object_records:
        sobject_type = str(record["SobjectType"])
        if sobject_type not in resources_by_name:
            continue
        edges.extend(build_object_permission_edges(record, muting_profile_ids=muting_profile_ids))
    filtered_field_records = [record for record in field_records if str(record["SobjectType"]) in resources_by_name]
    edges.extend(build_field_permission_edges(filtered_field_records, muting_profile_ids=muting_profile_ids))
    await merge_profile_permissions(edges)
    logger.info("merged_profile_permissions count=%s", len(edges))
