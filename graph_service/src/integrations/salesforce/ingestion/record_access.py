"""Salesforce record-level Share access → subject HAS_PERMISSION edges."""

from __future__ import annotations

import logging
from typing import Any, Literal

from simple_salesforce import Salesforce

from integrations.salesforce.client import describe_global, query_all
from integrations.salesforce.ingestion.groups import ensure_groups_for_ids
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    RecordPermissionEdgeRow,
    merge_record_permissions,
)
from integrations.salesforce.ingestion.users import ensure_identities_for_ids
from integrations.salesforce.models import (
    PERMISSION_EFFECT_GRANT,
    build_record_permission_extra,
)
from integrations.salesforce.settings import get_salesforce_settings
from integrations.salesforce.soql import build_share_table_soql

logger = logging.getLogger(__name__)

_ALLOWED_ROW_CAUSES = frozenset(
    {
        "Owner",
        "Manual",
        "Rule",
        "Team",
        "ImplicitChild",
        "ImplicitParent",
        "AssociatedRecord",
        "ManualUserTeam",
        "ManualGroupTeam",
        "Territory",
        "TerritoryManual",
        "TerritoryRule",
    }
)

_ACCESS_LEVEL_MAP = {
    "Read": "read",
    "Edit": "edit",
    "All": "all",
}


def share_object_name_for_sobject(sobject_name: str) -> str:
    if sobject_name.endswith("__c"):
        return f"{sobject_name[:-3]}__Share"
    return f"{sobject_name}Share"


def discover_share_objects(
    sf: Salesforce,
    *,
    allowlist: frozenset[str],
) -> list[tuple[str, str]]:
    """Return (share_object_api_name, target_sobject_api_name) pairs."""
    discovered: list[tuple[str, str]] = []
    for summary in describe_global(sf):
        name = summary.get("name")
        if not isinstance(name, str) or not name.endswith("Share"):
            continue
        if allowlist and name not in allowlist:
            continue
        if not summary.get("queryable"):
            continue
        if name.endswith("__Share"):
            target = name[: -len("__Share")] + "__c"
        else:
            target = name[: -len("Share")]
        discovered.append((name, target))
    return discovered


def map_share_access_level(access_level: str | None) -> str:
    if not access_level:
        return "read"
    return _ACCESS_LEVEL_MAP.get(str(access_level), str(access_level).lower())


_ACCESS_LEVEL_FIELDS = (
    "AccessLevel",
    "CaseAccessLevel",
    "OpportunityAccessLevel",
    "AccountAccessLevel",
    "LeadAccessLevel",
    "ContactAccessLevel",
)


def _extract_access_level(share_row: dict[str, Any]) -> str | None:
    for field_name in _ACCESS_LEVEL_FIELDS:
        value = share_row.get(field_name)
        if value:
            return str(value)
    return None


def build_record_permission_edge(
    share_row: dict[str, Any],
    *,
    target_sobject: str,
) -> RecordPermissionEdgeRow | None:
    user_or_group_id = share_row.get("UserOrGroupId")
    row_cause = str(share_row.get("RowCause") or "")
    if not user_or_group_id or row_cause not in _ALLOWED_ROW_CAUSES:
        return None
    subject_id = str(user_or_group_id)
    if subject_id.startswith("005"):
        subject_kind: Literal["identity", "group"] = "identity"
    elif subject_id.startswith("00G"):
        subject_kind = "group"
    else:
        return None
    parent_field = parent_id_field_for_sobject(target_sobject)
    record_id = str(share_row.get(parent_field) or share_row.get("ParentId") or share_row.get("Id") or "")
    if not record_id:
        return None
    access_level = map_share_access_level(_extract_access_level(share_row))
    extra = build_record_permission_extra(
        record_id=record_id,
        row_cause=row_cause,
        access_level=access_level,
    )
    return RecordPermissionEdgeRow(
        subject_kind=subject_kind,
        subject_external_id=subject_id,
        subject_app=SALESFORCE_APP,
        resource_external_id=target_sobject,
        permission=access_level,
        effect=PERMISSION_EFFECT_GRANT,
        extra=extra,
    )


def parent_id_field_for_sobject(sobject_name: str) -> str:
    if sobject_name.endswith("__c"):
        return "ParentId"
    return f"{sobject_name}Id"


def share_soql(share_object_name: str, *, target_sobject: str) -> str:
    return build_share_table_soql(
        share_object_name=share_object_name,
        target_sobject=target_sobject,
    )


async def ingest_record_access(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    resources_by_name: dict[str, str],
    known_identity_ids: set[str],
    known_group_ids: set[str],
) -> None:
    settings = get_salesforce_settings()
    share_pairs = discover_share_objects(sf, allowlist=settings.share_object_allowlist)
    if settings.share_object_allowlist:
        logger.info("record_access_allowlist count=%s", len(share_pairs))
    edges: list[RecordPermissionEdgeRow] = []
    referenced_user_ids: set[str] = set()
    referenced_group_ids: set[str] = set()

    for share_object_name, target_sobject in share_pairs:
        if target_sobject not in resources_by_name:
            continue
        try:
            share_rows = query_all(sf, share_soql(share_object_name, target_sobject=target_sobject))
        except Exception as exc:
            logger.warning("record_access_skip share_object=%s error=%s", share_object_name, exc)
            continue
        for share_row in share_rows:
            edge = build_record_permission_edge(share_row, target_sobject=target_sobject)
            if edge is None:
                continue
            if edge["subject_kind"] == "identity":
                referenced_user_ids.add(edge["subject_external_id"])
            else:
                referenced_group_ids.add(edge["subject_external_id"])
            edges.append(edge)

    await ensure_identities_for_ids(
        sf,
        connection=connection,
        user_ids=referenced_user_ids,
        known_identity_ids=known_identity_ids,
    )
    await ensure_groups_for_ids(
        sf,
        connection=connection,
        group_ids=referenced_group_ids,
        known_group_ids=known_group_ids,
    )
    await merge_record_permissions(edges)
    logger.info("merged_record_permissions count=%s", len(edges))
