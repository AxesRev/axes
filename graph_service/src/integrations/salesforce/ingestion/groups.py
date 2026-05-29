"""Salesforce group ingestion → Group nodes and MEMBER_OF edges."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ids import graph_subject_from_user_or_group_id
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    GroupRow,
    MemberOfRow,
    merge_groups,
    merge_member_of,
)
from integrations.salesforce.models import SalesforceGroupExtra
from integrations.salesforce.soql import build_group_by_ids_soql

logger = logging.getLogger(__name__)

_GROUP_SOQL = """
SELECT Id, Name, DeveloperName, Type
FROM Group
WHERE Type IN ('Regular', 'Role', 'RoleAndSubordinatesInternal')
"""

_GROUP_MEMBER_SOQL = """
SELECT Id, GroupId, UserOrGroupId
FROM GroupMember
"""


def _group_kind(group_type: str) -> str:
    if group_type == "Regular":
        return "public_group"
    return "role_group"


def group_row_from_record(group: dict[str, Any], *, connection: ConnectionRef) -> GroupRow:
    group_type = str(group.get("Type") or "Regular")
    extra = SalesforceGroupExtra(kind=_group_kind(group_type))  # type: ignore[arg-type]
    return GroupRow(
        external_id=str(group["Id"]),
        name=str(group.get("DeveloperName") or group.get("Name") or group["Id"]),
        description=str(group.get("Name") or ""),
        extra=extra.model_dump(),
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


def build_group_member_rows(
    members: list[dict[str, Any]],
    *,
    known_user_ids: set[str],
    known_group_ids: set[str],
) -> list[MemberOfRow]:
    rows: list[MemberOfRow] = []
    for member in members:
        group_id = str(member["GroupId"])
        member_id = str(member["UserOrGroupId"])
        subject = graph_subject_from_user_or_group_id(member_id)
        if subject is None:
            continue
        if subject.kind == "identity" and subject.external_id not in known_user_ids:
            continue
        if subject.kind == "group" and subject.external_id not in known_group_ids:
            continue
        rows.append(
            MemberOfRow(
                member_kind=subject.kind,
                member_external_id=subject.external_id,
                member_app=SALESFORCE_APP,
                group_external_id=group_id,
            )
        )
    return rows


async def ingest_groups(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    identity_external_ids: dict[str, str],
) -> dict[str, str]:
    groups = query_all(sf, _GROUP_SOQL)
    members = query_all(sf, _GROUP_MEMBER_SOQL)
    group_rows = [group_row_from_record(group, connection=connection) for group in groups]
    await merge_groups(group_rows)
    known_user_ids = set(identity_external_ids.values())
    known_group_ids = {row["external_id"] for row in group_rows}
    member_rows = build_group_member_rows(
        members,
        known_user_ids=known_user_ids,
        known_group_ids=known_group_ids,
    )
    await merge_member_of(member_rows)
    groups_by_name = {row["name"]: row["external_id"] for row in group_rows}
    logger.info("merged_groups count=%s member_edges=%s", len(group_rows), len(member_rows))
    return groups_by_name


async def ensure_groups_for_ids(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    group_ids: set[str],
    known_group_ids: set[str],
) -> None:
    missing = sorted(group_ids - known_group_ids)
    if not missing:
        return
    groups = query_all(sf, build_group_by_ids_soql(missing))
    rows = [group_row_from_record(group, connection=connection) for group in groups]
    if rows:
        await merge_groups(rows)
        logger.info("ensure_groups_for_ids added=%s", len(rows))
