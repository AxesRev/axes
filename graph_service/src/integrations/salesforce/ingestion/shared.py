"""Shared constants and batch graph helpers for Salesforce ingestion."""

from __future__ import annotations

import json
import logging
from typing import Literal, TypedDict

from neomodel import adb

logger = logging.getLogger(__name__)

SALESFORCE_APP = "salesforce"
PERMISSION_BATCH_SIZE = 500


class ConnectionRef(TypedDict):
    app: str
    external_id: str


class TenantRow(TypedDict):
    external_id: str
    name: str


class AppConnectionRow(TypedDict):
    app: str
    external_id: str
    name: str
    extra: dict[str, object]


class ConnectionTenantRow(TypedDict):
    app: str
    connection_external_id: str
    tenant_external_id: str


class ResourceRow(TypedDict):
    external_id: str
    name: str
    uri: str
    kind: str
    connection_app: str
    connection_external_id: str


class AppIdentityRow(TypedDict):
    app: str
    external_id: str
    name: str
    extra: dict[str, object]
    connection_app: str
    connection_external_id: str


class GroupRow(TypedDict):
    external_id: str
    name: str
    description: str
    extra: dict[str, object]
    connection_app: str
    connection_external_id: str


class ProfileRow(TypedDict):
    app: str
    external_id: str
    name: str
    description: str
    extra: dict[str, object]
    connection_app: str
    connection_external_id: str


class MemberOfRow(TypedDict):
    member_kind: Literal["identity", "group"]
    member_external_id: str
    member_app: str
    group_external_id: str


class ManagerOfRow(TypedDict):
    manager_app: str
    manager_external_id: str
    report_app: str
    report_external_id: str


class AssignedProfileRow(TypedDict):
    subject_kind: Literal["identity", "group"]
    subject_external_id: str
    subject_app: str
    profile_app: str
    profile_external_id: str


class ProfileMemberOfRow(TypedDict):
    child_profile_external_id: str
    child_profile_app: str
    parent_profile_external_id: str
    parent_profile_app: str


class ProfilePermissionEdgeRow(TypedDict):
    profile_external_id: str
    profile_app: str
    resource_external_id: str
    permission: str
    effect: str
    extra: dict[str, object]


class RecordPermissionEdgeRow(TypedDict):
    subject_kind: Literal["identity", "group"]
    subject_external_id: str
    subject_app: str
    resource_external_id: str
    permission: str
    effect: str
    extra: dict[str, object]


def json_property(value: dict[str, object]) -> str:
    """Serialize JSONProperty payloads the same way neomodel stores them."""
    return json.dumps(value)


def _connection_rows_for_cypher(rows: list[AppConnectionRow]) -> list[dict[str, object]]:
    return [
        {
            "app": row["app"],
            "external_id": row["external_id"],
            "name": row["name"],
            "extra": json_property(row["extra"]),
        }
        for row in rows
    ]


def _identity_rows_for_cypher(rows: list[AppIdentityRow]) -> list[dict[str, object]]:
    return [
        {
            "app": row["app"],
            "external_id": row["external_id"],
            "name": row["name"],
            "extra": json_property(row["extra"]),
            "connection_app": row["connection_app"],
            "connection_external_id": row["connection_external_id"],
        }
        for row in rows
    ]


def _group_rows_for_cypher(rows: list[GroupRow]) -> list[dict[str, object]]:
    return [
        {
            "external_id": row["external_id"],
            "name": row["name"],
            "description": row["description"],
            "extra": json_property(row["extra"]),
            "connection_app": row["connection_app"],
            "connection_external_id": row["connection_external_id"],
        }
        for row in rows
    ]


def _profile_rows_for_cypher(rows: list[ProfileRow]) -> list[dict[str, object]]:
    return [
        {
            "app": row["app"],
            "external_id": row["external_id"],
            "name": row["name"],
            "description": row["description"],
            "extra": json_property(row["extra"]),
            "connection_app": row["connection_app"],
            "connection_external_id": row["connection_external_id"],
        }
        for row in rows
    ]


def _profile_permission_rows_for_cypher(
    rows: list[ProfilePermissionEdgeRow],
) -> list[dict[str, object]]:
    return [
        {
            "profile_external_id": row["profile_external_id"],
            "profile_app": row["profile_app"],
            "resource_external_id": row["resource_external_id"],
            "permission": row["permission"],
            "effect": row["effect"],
            "extra": json_property(row["extra"]),
        }
        for row in rows
    ]


def _record_permission_rows_for_cypher(
    rows: list[RecordPermissionEdgeRow],
) -> list[dict[str, object]]:
    return [
        {
            "subject_kind": row["subject_kind"],
            "subject_external_id": row["subject_external_id"],
            "subject_app": row["subject_app"],
            "resource_external_id": row["resource_external_id"],
            "permission": row["permission"],
            "effect": row["effect"],
            "extra": json_property(row["extra"]),
        }
        for row in rows
    ]


async def _run_batched_query(
    query: str,
    rows: list[object],
    *,
    params: dict[str, object] | None = None,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    if not rows:
        return

    base_params = params or {}
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        await adb.cypher_query(query, {"rows": batch, **base_params})


async def merge_tenants(rows: list[TenantRow], *, batch_size: int = PERMISSION_BATCH_SIZE) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (t:Tenant {external_id: row.external_id})
    SET t.name = row.name
    """
    await _run_batched_query(query, rows, batch_size=batch_size)


async def merge_app_connections(
    rows: list[AppConnectionRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (c:AppConnection {app: row.app, external_id: row.external_id})
    SET c.name = row.name, c.extra = row.extra
    """
    await _run_batched_query(query, _connection_rows_for_cypher(rows), batch_size=batch_size)


async def merge_connections_belong_to_tenants(
    rows: list[ConnectionTenantRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    query = """
    UNWIND $rows AS row
    MATCH (c:AppConnection {app: row.app, external_id: row.connection_external_id})
    MATCH (t:Tenant {external_id: row.tenant_external_id})
    MERGE (c)-[:BELONGS_TO]->(t)
    """
    await _run_batched_query(query, rows, batch_size=batch_size)


async def merge_resources(rows: list[ResourceRow], *, batch_size: int = PERMISSION_BATCH_SIZE) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (r:Resource {external_id: row.external_id})
    SET r.name = row.name, r.uri = row.uri, r.kind = row.kind
    WITH r, row
    MATCH (c:AppConnection {app: row.connection_app, external_id: row.connection_external_id})
    MERGE (r)-[:BELONGS_TO]->(c)
    """
    await _run_batched_query(query, rows, batch_size=batch_size)


async def merge_app_identities(
    rows: list[AppIdentityRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (i:AppIdentity {app: row.app, external_id: row.external_id})
    SET i.name = row.name, i.extra = row.extra
    WITH i, row
    MATCH (c:AppConnection {app: row.connection_app, external_id: row.connection_external_id})
    MERGE (i)-[:BELONGS_TO]->(c)
    """
    await _run_batched_query(query, _identity_rows_for_cypher(rows), batch_size=batch_size)


async def merge_groups(rows: list[GroupRow], *, batch_size: int = PERMISSION_BATCH_SIZE) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (g:Group {external_id: row.external_id})
    SET g.name = row.name, g.description = row.description, g.extra = row.extra
    WITH g, row
    MATCH (c:AppConnection {app: row.connection_app, external_id: row.connection_external_id})
    MERGE (g)-[:BELONGS_TO]->(c)
    """
    await _run_batched_query(query, _group_rows_for_cypher(rows), batch_size=batch_size)


async def merge_profiles(rows: list[ProfileRow], *, batch_size: int = PERMISSION_BATCH_SIZE) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (p:Profile {app: row.app, external_id: row.external_id})
    SET p.name = row.name, p.description = row.description, p.extra = row.extra
    WITH p, row
    MATCH (c:AppConnection {app: row.connection_app, external_id: row.connection_external_id})
    MERGE (p)-[:BELONGS_TO]->(c)
    """
    await _run_batched_query(query, _profile_rows_for_cypher(rows), batch_size=batch_size)


async def merge_member_of(rows: list[MemberOfRow], *, batch_size: int = PERMISSION_BATCH_SIZE) -> None:
    identity_rows = [row for row in rows if row["member_kind"] == "identity"]
    group_rows = [row for row in rows if row["member_kind"] == "group"]

    if identity_rows:
        identity_query = """
        UNWIND $rows AS row
        MATCH (member:AppIdentity {app: row.member_app, external_id: row.member_external_id})
        MATCH (group:Group {external_id: row.group_external_id})
        MERGE (member)-[:MEMBER_OF]->(group)
        """
        await _run_batched_query(identity_query, identity_rows, batch_size=batch_size)

    if group_rows:
        group_query = """
        UNWIND $rows AS row
        MATCH (member:Group {external_id: row.member_external_id})
        MATCH (group:Group {external_id: row.group_external_id})
        MERGE (member)-[:MEMBER_OF]->(group)
        """
        await _run_batched_query(group_query, group_rows, batch_size=batch_size)


async def merge_manager_of(rows: list[ManagerOfRow], *, batch_size: int = PERMISSION_BATCH_SIZE) -> None:
    query = """
    UNWIND $rows AS row
    MATCH (manager:AppIdentity {app: row.manager_app, external_id: row.manager_external_id})
    MATCH (report:AppIdentity {app: row.report_app, external_id: row.report_external_id})
    MERGE (manager)-[:MANAGER_OF]->(report)
    """
    await _run_batched_query(query, rows, batch_size=batch_size)


async def merge_assigned_profile(
    rows: list[AssignedProfileRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    identity_rows = [row for row in rows if row["subject_kind"] == "identity"]
    group_rows = [row for row in rows if row["subject_kind"] == "group"]

    if identity_rows:
        identity_query = """
        UNWIND $rows AS row
        MATCH (subject:AppIdentity {app: row.subject_app, external_id: row.subject_external_id})
        MATCH (profile:Profile {app: row.profile_app, external_id: row.profile_external_id})
        MERGE (subject)-[:ASSIGNED_PROFILE]->(profile)
        """
        await _run_batched_query(identity_query, identity_rows, batch_size=batch_size)

    if group_rows:
        group_query = """
        UNWIND $rows AS row
        MATCH (subject:Group {external_id: row.subject_external_id})
        MATCH (profile:Profile {app: row.profile_app, external_id: row.profile_external_id})
        MERGE (subject)-[:ASSIGNED_PROFILE]->(profile)
        """
        await _run_batched_query(group_query, group_rows, batch_size=batch_size)


async def merge_profile_member_of(
    rows: list[ProfileMemberOfRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    query = """
    UNWIND $rows AS row
    MATCH (child:Profile {app: row.child_profile_app, external_id: row.child_profile_external_id})
    MATCH (parent:Profile {app: row.parent_profile_app, external_id: row.parent_profile_external_id})
    MERGE (child)-[:MEMBER_OF]->(parent)
    """
    await _run_batched_query(query, rows, batch_size=batch_size)


async def merge_profile_permissions(
    rows: list[ProfilePermissionEdgeRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    query = """
    UNWIND $rows AS row
    MATCH (profile:Profile {app: row.profile_app, external_id: row.profile_external_id})
    MATCH (resource:Resource {external_id: row.resource_external_id})
    MERGE (profile)-[hp:HAS_PERMISSION]->(resource)
    SET hp.permission = row.permission, hp.effect = row.effect, hp.extra = row.extra
    """
    await _run_batched_query(
        query,
        _profile_permission_rows_for_cypher(rows),
        batch_size=batch_size,
    )


async def merge_record_permissions(
    rows: list[RecordPermissionEdgeRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    identity_rows = [row for row in rows if row["subject_kind"] == "identity"]
    group_rows = [row for row in rows if row["subject_kind"] == "group"]

    if identity_rows:
        identity_query = """
        UNWIND $rows AS row
        MATCH (subject:AppIdentity {app: row.subject_app, external_id: row.subject_external_id})
        MATCH (resource:Resource {external_id: row.resource_external_id})
        MERGE (subject)-[hp:HAS_PERMISSION]->(resource)
        SET hp.permission = row.permission, hp.effect = row.effect, hp.extra = row.extra
        """
        await _run_batched_query(
            identity_query,
            _record_permission_rows_for_cypher(identity_rows),
            batch_size=batch_size,
        )

    if group_rows:
        group_query = """
        UNWIND $rows AS row
        MATCH (subject:Group {external_id: row.subject_external_id})
        MATCH (resource:Resource {external_id: row.resource_external_id})
        MERGE (subject)-[hp:HAS_PERMISSION]->(resource)
        SET hp.permission = row.permission, hp.effect = row.effect, hp.extra = row.extra
        """
        await _run_batched_query(
            group_query,
            _record_permission_rows_for_cypher(group_rows),
            batch_size=batch_size,
        )
