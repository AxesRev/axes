"""Salesforce record-level Share access → instance Resource + HAS_PERMISSION edges."""

from __future__ import annotations

import logging

from common.permissions import PERMISSION_EFFECT_GRANT
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest

from integrations.salesforce.client import query_all
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
from integrations.salesforce.soql import build_share_table_soql

logger = logging.getLogger(__name__)


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
