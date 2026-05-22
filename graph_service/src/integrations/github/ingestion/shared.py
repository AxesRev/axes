"""Shared constants and batch graph helpers for GitHub ingestion."""

from __future__ import annotations

import json
import logging
from typing import Literal, TypedDict

from github import Auth, GithubIntegration
from neomodel import adb

from integrations.github.settings import get_github_settings

logger = logging.getLogger(__name__)

GITHUB_APP = "github"
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
    connection_app: str
    connection_external_id: str


class MemberOfRow(TypedDict):
    member_kind: Literal["identity", "group"]
    member_external_id: str
    member_app: str
    group_external_id: str


class PermissionEdgeRow(TypedDict):
    subject_kind: Literal["user", "team"]
    subject_external_id: str
    resource_external_id: str
    permission: str


def make_github_integration() -> GithubIntegration:
    settings = get_github_settings()
    auth = Auth.AppAuth(settings.GITHUB_APP_ID, settings.private_key)
    return GithubIntegration(auth=auth)


def gql_string(value: str) -> str:
    return json.dumps(value)


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


async def _run_batched_query(
    query: str,
    rows: list[object],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    if not rows:
        return

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        await adb.cypher_query(query, {"rows": batch})


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
    SET g.name = row.name, g.description = row.description
    WITH g, row
    MATCH (c:AppConnection {app: row.connection_app, external_id: row.connection_external_id})
    MERGE (g)-[:BELONGS_TO]->(c)
    """
    await _run_batched_query(query, rows, batch_size=batch_size)


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


async def merge_resource_permissions(
    rows: list[PermissionEdgeRow],
    *,
    batch_size: int = PERMISSION_BATCH_SIZE,
) -> None:
    user_rows = [row for row in rows if row["subject_kind"] == "user"]
    team_rows = [row for row in rows if row["subject_kind"] == "team"]

    if user_rows:
        user_query = """
        UNWIND $rows AS row
        MATCH (subject:AppIdentity {app: $app, external_id: row.subject_external_id})
        MATCH (resource:Resource {external_id: row.resource_external_id})
        MERGE (subject)-[hp:HAS_PERMISSION]->(resource)
        SET hp.permission = row.permission
        """
        for start in range(0, len(user_rows), batch_size):
            batch = user_rows[start : start + batch_size]
            await adb.cypher_query(user_query, {"rows": batch, "app": GITHUB_APP})

    if team_rows:
        team_query = """
        UNWIND $rows AS row
        MATCH (subject:Group {external_id: row.subject_external_id})
        MATCH (resource:Resource {external_id: row.resource_external_id})
        MERGE (subject)-[hp:HAS_PERMISSION]->(resource)
        SET hp.permission = row.permission
        """
        await _run_batched_query(team_query, team_rows, batch_size=batch_size)
