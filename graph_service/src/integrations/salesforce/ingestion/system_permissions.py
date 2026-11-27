"""Salesforce system permissions → Scope nodes (kind system_permission) and Profile HAS_PERMISSION edges.

Every ``Permissions*`` boolean on PermissionSet (API Enabled, Export Reports, Modify All Data, …) becomes
one Scope, whether or not anything grants it, so a request for an org-wide ability has a target.
"""

from __future__ import annotations

import logging
from typing import Any

from common.graph_schema import SCOPE_KIND_SYSTEM_PERMISSION
from common.permissions import PERMISSION_ENABLED
from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.permissions import (
    fetch_muting_profile_ids,
    fetch_profile_id_by_owned_permission_set,
    permission_effect,
    remap_parent_to_profile,
)
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    ProfilePermissionEdgeRow,
    ScopeRow,
    merge_profile_permissions,
    merge_scopes,
    scope_external_id,
)
from integrations.salesforce.models import build_system_permission_extra

logger = logging.getLogger(__name__)

_PERMISSION_FIELD_PREFIX = "Permissions"
# Keep each SOQL short enough for a GET URL; PermissionSet has ~670 permission fields.
_FIELDS_PER_QUERY = 150


def system_permission_fields(describe_fields: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return (api_name, label) for boolean ``Permissions*`` fields, sorted by api name."""
    fields: list[tuple[str, str]] = []
    for field in describe_fields:
        name = field.get("name")
        if not isinstance(name, str) or not name.startswith(_PERMISSION_FIELD_PREFIX):
            continue
        if field.get("type") != "boolean":
            continue
        fields.append((name, str(field.get("label") or name)))
    return sorted(fields)


def system_permission_scope_id(connection: ConnectionRef, api_name: str) -> str:
    # Prefixed so a permission can never collide with an SObject-named scope.
    return scope_external_id(connection, f"permission:{api_name.removeprefix(_PERMISSION_FIELD_PREFIX)}")


def system_permission_scope_rows(connection: ConnectionRef, fields: list[tuple[str, str]]) -> list[ScopeRow]:
    return [
        ScopeRow(
            external_id=system_permission_scope_id(connection, api_name),
            name=label,
            kind=SCOPE_KIND_SYSTEM_PERMISSION,
            connection_app=connection["app"],
            connection_external_id=connection["external_id"],
        )
        for api_name, label in fields
    ]


def fetch_permission_set_flags(sf: Salesforce, field_names: list[str]) -> list[dict[str, Any]]:
    """Return one row per PermissionSet with every requested flag, querying the fields in chunks."""
    rows_by_id: dict[str, dict[str, Any]] = {}
    for start in range(0, len(field_names), _FIELDS_PER_QUERY):
        chunk = field_names[start : start + _FIELDS_PER_QUERY]
        soql = "SELECT Id, " + ", ".join(chunk) + " FROM PermissionSet"  # nosec B608 - names come from describe
        for record in query_all(sf, soql):
            row = rows_by_id.setdefault(str(record["Id"]), {"ParentId": str(record["Id"])})
            row.update({name: record.get(name) for name in chunk})
    return list(rows_by_id.values())


def build_system_permission_edges(
    rows: list[dict[str, Any]],
    *,
    connection: ConnectionRef,
    field_names: list[str],
    muting_profile_ids: set[str],
) -> list[ProfilePermissionEdgeRow]:
    edges: list[ProfilePermissionEdgeRow] = []
    for row in rows:
        profile_id = str(row["ParentId"])
        effect = permission_effect(profile_id, muting_profile_ids)
        for api_name in field_names:
            if row.get(api_name) is True:
                edges.append(
                    ProfilePermissionEdgeRow(
                        profile_external_id=profile_id,
                        profile_app=SALESFORCE_APP,
                        resource_external_id=system_permission_scope_id(connection, api_name),
                        permission=PERMISSION_ENABLED,
                        effect=effect,
                        extra=build_system_permission_extra(api_name),
                    )
                )
    return edges


async def ingest_system_permissions(sf: Salesforce, *, connection: ConnectionRef) -> None:
    fields = system_permission_fields(list(sf.PermissionSet.describe().get("fields", [])))
    await merge_scopes(system_permission_scope_rows(connection, fields))

    field_names = [api_name for api_name, _label in fields]
    rows = remap_parent_to_profile(
        fetch_permission_set_flags(sf, field_names),
        fetch_profile_id_by_owned_permission_set(sf),
    )
    edges = build_system_permission_edges(
        rows,
        connection=connection,
        field_names=field_names,
        muting_profile_ids=fetch_muting_profile_ids(sf),
    )
    await merge_profile_permissions(edges)
    logger.info("merged_system_permissions scopes=%s edges=%s", len(fields), len(edges))
