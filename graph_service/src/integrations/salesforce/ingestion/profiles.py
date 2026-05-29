"""Salesforce profile bundle ingestion → Profile nodes."""

from __future__ import annotations

import logging
from typing import Any, Literal

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all, query_muting_permission_set_links
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    ConnectionRef,
    ProfileMemberOfRow,
    ProfileRow,
    merge_profile_member_of,
    merge_profiles,
)
from integrations.salesforce.models import SalesforceProfileExtra

logger = logging.getLogger(__name__)

_PROFILE_SOQL = "SELECT Id, Name, Description FROM Profile"
_PERMISSION_SET_SOQL = """
SELECT Id, Name, Description, IsOwnedByProfile
FROM PermissionSet
WHERE IsOwnedByProfile = false
"""
_PERMISSION_SET_GROUP_SOQL = "SELECT Id, MasterLabel, Description FROM PermissionSetGroup"
_GROUP_COMPONENT_SOQL = "SELECT Id, PermissionSetGroupId, PermissionSetId FROM PermissionSetGroupComponent"


def _profile_row(
    *,
    external_id: str,
    name: str,
    description: str,
    kind: Literal["profile", "permission_set", "permission_set_group", "muting_permission_set"],
    connection: ConnectionRef,
) -> ProfileRow:
    extra = SalesforceProfileExtra(kind=kind)
    return ProfileRow(
        app=SALESFORCE_APP,
        external_id=external_id,
        name=name,
        description=description,
        extra=extra.model_dump(),
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


def build_profile_member_of_rows(components: list[dict[str, Any]]) -> list[ProfileMemberOfRow]:
    rows: list[ProfileMemberOfRow] = []
    for component in components:
        rows.append(
            ProfileMemberOfRow(
                child_profile_external_id=str(component["PermissionSetId"]),
                child_profile_app=SALESFORCE_APP,
                parent_profile_external_id=str(component["PermissionSetGroupId"]),
                parent_profile_app=SALESFORCE_APP,
            )
        )
    return rows


async def ingest_profiles(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
) -> dict[str, str]:
    profiles = query_all(sf, _PROFILE_SOQL)
    permission_sets = query_all(sf, _PERMISSION_SET_SOQL)
    permission_set_groups = query_all(sf, _PERMISSION_SET_GROUP_SOQL)
    components = query_all(sf, _GROUP_COMPONENT_SOQL)
    muting_links = query_muting_permission_set_links(sf)

    muting_permission_set_ids = {str(row["PermissionSetId"]) for row in muting_links}
    rows: list[ProfileRow] = []
    for profile in profiles:
        rows.append(
            _profile_row(
                external_id=str(profile["Id"]),
                name=str(profile.get("Name") or profile["Id"]),
                description=str(profile.get("Description") or ""),
                kind="profile",
                connection=connection,
            )
        )
    for permission_set in permission_sets:
        permission_set_id = str(permission_set["Id"])
        kind: Literal["permission_set", "muting_permission_set"]
        if permission_set_id in muting_permission_set_ids:
            kind = "muting_permission_set"
        else:
            kind = "permission_set"
        rows.append(
            _profile_row(
                external_id=permission_set_id,
                name=str(permission_set.get("Name") or permission_set_id),
                description=str(permission_set.get("Description") or ""),
                kind=kind,
                connection=connection,
            )
        )
    for group in permission_set_groups:
        rows.append(
            _profile_row(
                external_id=str(group["Id"]),
                name=str(group.get("MasterLabel") or group["Id"]),
                description=str(group.get("Description") or ""),
                kind="permission_set_group",
                connection=connection,
            )
        )

    await merge_profiles(rows)
    member_rows = build_profile_member_of_rows(components)
    await merge_profile_member_of(member_rows)
    profiles_by_id = {row["external_id"]: row["external_id"] for row in rows}
    logger.info(
        "merged_profiles count=%s profile_member_of=%s",
        len(rows),
        len(member_rows),
    )
    return profiles_by_id
