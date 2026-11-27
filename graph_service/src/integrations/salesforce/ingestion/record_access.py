"""Salesforce record-level Share access → instance Resource + HAS_PERMISSION edges."""

from __future__ import annotations

import logging

from common.permissions import PERMISSION_EFFECT_GRANT
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest

from integrations.salesforce.client import describe_name_field, query_all
from integrations.salesforce.ingestion.groups import ensure_groups_for_ids
from integrations.salesforce.ingestion.resources import resource_row_from_record
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    RecordPermissionEdgeRow,
    ResourceRow,
    merge_record_permissions,
    merge_resources,
)
from integrations.salesforce.ingestion.users import ensure_identities_for_ids
from integrations.salesforce.models import build_record_permission_extra
from integrations.salesforce.settings import get_salesforce_settings
from integrations.salesforce.share_objects import (
    NormalizedShareAccess,
    describe_share_table,
    discover_share_pairs,
    normalize_share_access,
)
from integrations.salesforce.soql import build_record_names_soql, build_share_table_soql

logger = logging.getLogger(__name__)

_NAME_LOOKUP_BATCH = 200


def fetch_record_names(sf: Salesforce, sobject: str, record_ids: list[str]) -> dict[str, str]:
    """Record Id -> display name (the sObject's name field), so the agent can match requests by name."""
    name_field = describe_name_field(sf, sobject)
    if not name_field:
        return {}
    names: dict[str, str] = {}
    for start in range(0, len(record_ids), _NAME_LOOKUP_BATCH):
        batch = record_ids[start : start + _NAME_LOOKUP_BATCH]
        try:
            rows = query_all(sf, build_record_names_soql(sobject=sobject, name_field=name_field, ids=batch))
        except SalesforceMalformedRequest as exc:
            logger.warning("record_names_skip sobject=%s error=%s", sobject, exc)
            return names
        for row in rows:
            if row.get(name_field):
                names[str(row["Id"])] = str(row[name_field])
    return names


def record_permission_edge_from_share_access(access: NormalizedShareAccess) -> RecordPermissionEdgeRow:
    return RecordPermissionEdgeRow(
        subject_kind=access.subject.kind,
        subject_external_id=access.subject.external_id,
        subject_app=SALESFORCE_APP,
        resource_external_id=access.record_id,
        permission=access.access_level,
        effect=PERMISSION_EFFECT_GRANT,
        extra=build_record_permission_extra(
            record_id=access.record_id,
            row_cause=access.row_cause,
            access_level=access.access_level,
        ),
    )


async def ingest_record_access(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    scopes_by_name: dict[str, str],
    known_identity_ids: set[str],
    known_group_ids: set[str],
) -> None:
    settings = get_salesforce_settings()
    share_pairs = discover_share_pairs(sf, allowlist=settings.share_object_allowlist)
    if settings.share_object_allowlist:
        logger.info("record_access_allowlist count=%s", len(share_pairs))

    instance_rows: dict[str, ResourceRow] = {}
    edges: list[RecordPermissionEdgeRow] = []
    referenced_user_ids: set[str] = set()
    referenced_group_ids: set[str] = set()

    for share_object_name, target_sobject in share_pairs:
        if target_sobject not in scopes_by_name:
            continue
        shape = describe_share_table(
            sf,
            share_object_name=share_object_name,
            target_sobject=target_sobject,
        )
        if shape is None:
            logger.debug(
                "record_access_skip_unrecognized_share_table share_object=%s",
                share_object_name,
            )
            continue
        try:
            share_rows = query_all(
                sf,
                build_share_table_soql(
                    share_object_name=shape.share_object_name,
                    parent_id_field=shape.parent_id_field,
                    access_level_field=shape.access_level_field,
                ),
            )
        except SalesforceMalformedRequest as exc:
            logger.warning("record_access_skip share_object=%s error=%s", share_object_name, exc)
            continue

        for share_row in share_rows:
            access = normalize_share_access(
                share_row,
                target_sobject=target_sobject,
                parent_id_field=shape.parent_id_field,
                access_level_field=shape.access_level_field,
            )
            if access is None:
                continue
            instance_rows[access.record_id] = resource_row_from_record(
                access.record_id,
                sobject_type=target_sobject,
                connection=connection,
            )
            edges.append(record_permission_edge_from_share_access(access))
            if access.subject.kind == "identity":
                referenced_user_ids.add(access.subject.external_id)
            else:
                referenced_group_ids.add(access.subject.external_id)

    ids_by_sobject: dict[str, list[str]] = {}
    for record_id, row in instance_rows.items():
        ids_by_sobject.setdefault(row["kind"], []).append(record_id)
    for sobject, record_ids in ids_by_sobject.items():
        names = fetch_record_names(sf, sobject, record_ids)
        for record_id, name in names.items():
            instance_rows[record_id] = resource_row_from_record(
                record_id,
                sobject_type=sobject,
                connection=connection,
                name=name,
            )
        logger.info("record_names sobject=%s records=%s named=%s", sobject, len(record_ids), len(names))

    await merge_resources(list(instance_rows.values()))
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
    logger.info(
        "merged_record_permissions count=%s instances=%s",
        len(edges),
        len(instance_rows),
    )
