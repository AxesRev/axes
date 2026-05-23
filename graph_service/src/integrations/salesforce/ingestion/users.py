"""Salesforce user ingestion → AppIdentity nodes."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    AppIdentityRow,
    ConnectionRef,
    merge_app_identities,
)
from integrations.salesforce.models import SalesforceAppIdentityExtra
from integrations.salesforce.soql import build_user_by_ids_soql

logger = logging.getLogger(__name__)

_USER_SOQL = """
SELECT Id, Username, Name, ProfileId, UserRoleId, ManagerId, IsActive
FROM User
WHERE IsActive = true
"""

_ROLE_SOQL = "SELECT Id, Name, DeveloperName FROM UserRole"


def _role_name_by_id(roles: list[dict[str, Any]]) -> dict[str, str]:
    return {str(row["Id"]): str(row.get("Name") or row.get("DeveloperName") or row["Id"]) for row in roles}


def identity_row_from_user(
    user: dict[str, Any],
    *,
    connection: ConnectionRef,
    role_name_by_id: dict[str, str],
) -> AppIdentityRow:
    role_id = user.get("UserRoleId")
    role_id_str = str(role_id) if role_id else None
    extra = SalesforceAppIdentityExtra(
        role_id=role_id_str,
        role_name=role_name_by_id.get(role_id_str) if role_id_str else None,
    )
    return AppIdentityRow(
        app=SALESFORCE_APP,
        external_id=str(user["Id"]),
        name=str(user.get("Username") or user.get("Name") or user["Id"]),
        extra=extra.model_dump(),
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


async def ingest_users(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
) -> dict[str, str]:
    users = query_all(sf, _USER_SOQL)
    roles = query_all(sf, _ROLE_SOQL)
    role_name_by_id = _role_name_by_id(roles)
    rows = [identity_row_from_user(user, connection=connection, role_name_by_id=role_name_by_id) for user in users]
    await merge_app_identities(rows)
    identity_external_ids = {row["external_id"]: row["external_id"] for row in rows}
    logger.info("merged_app_identities count=%s", len(rows))
    return identity_external_ids


async def ensure_identities_for_ids(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
    user_ids: set[str],
    known_identity_ids: set[str],
) -> None:
    missing = sorted(user_ids - known_identity_ids)
    if not missing:
        return

    users = query_all(sf, build_user_by_ids_soql(missing))
    roles = query_all(sf, _ROLE_SOQL)
    role_name_by_id = _role_name_by_id(roles)
    rows = [identity_row_from_user(user, connection=connection, role_name_by_id=role_name_by_id) for user in users]
    if rows:
        await merge_app_identities(rows)
        logger.info("ensure_identities_for_ids added=%s", len(rows))
