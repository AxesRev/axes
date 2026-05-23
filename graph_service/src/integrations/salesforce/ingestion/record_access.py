"""Salesforce record-level Share access → subject HAS_PERMISSION edges."""

from __future__ import annotations

import logging

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.groups import ensure_groups_for_ids
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    RecordPermissionEdgeRow,
    merge_record_permissions,
)
from integrations.salesforce.ingestion.users import ensure_identities_for_ids
from integrations.salesforce.models import PERMISSION_EFFECT_GRANT, build_record_permission_extra
from integrations.salesforce.settings import get_salesforce_settings
from integrations.salesforce.share_objects import NormalizedShareAccess, discover_share_pairs, normalize_share_access
from integrations.salesforce.soql import build_share_table_soql

logger = logging.getLogger(__name__)


def record_permission_edge_from_share_access(
    access: NormalizedShareAccess,
    *,
    target_sobject: str,
) -> RecordPermissionEdgeRow:
    return RecordPermissionEdgeRow(
        subject_kind=access.subject.kind,
        subject_external_id=access.subject.external_id,
        subject_app=SALESFORCE_APP,
        resource_external_id=target_sobject,
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
    resources_by_name: dict[str, str],
    known_identity_ids: set[str],
    known_group_ids: set[str],
) -> None:
    settings = get_salesforce_settings()
    share_pairs = discover_share_pairs(sf, allowlist=settings.share_object_allowlist)
    if settings.share_object_allowlist:
        logger.info("record_access_allowlist count=%s", len(share_pairs))

    edges: list[RecordPermissionEdgeRow] = []
    referenced_user_ids: set[str] = set()
    referenced_group_ids: set[str] = set()

    for share_object_name, target_sobject in share_pairs:
        if target_sobject not in resources_by_name:
            continue
        try:
            share_rows = query_all(
                sf,
                build_share_table_soql(
                    share_object_name=share_object_name,
                    target_sobject=target_sobject,
                ),
            )
        except SalesforceMalformedRequest as exc:
            logger.warning("record_access_skip share_object=%s error=%s", share_object_name, exc)
            continue

        for share_row in share_rows:
            access = normalize_share_access(share_row, target_sobject=target_sobject)
            if access is None:
                continue
            edge = record_permission_edge_from_share_access(access, target_sobject=target_sobject)
            if access.subject.kind == "identity":
                referenced_user_ids.add(access.subject.external_id)
            else:
                referenced_group_ids.add(access.subject.external_id)
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
