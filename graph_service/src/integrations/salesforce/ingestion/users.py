"""Salesforce user ingestion → AppIdentity nodes."""

from __future__ import annotations

import logging
from typing import Any

from simple_salesforce import Salesforce

from integrations.identity_correlation import correlate_app_identities_by_email, correlation_row_from_email
from integrations.salesforce.client import query_all
from integrations.salesforce.ingestion.shared import (
    SALESFORCE_APP,
    AppIdentityRow,
    ConnectionRef,
    merge_app_identities,
)
from integrations.salesforce.models import SalesforceAppIdentityExtra, SalesforceUserPermissionFlag
from integrations.salesforce.share_objects import validate_field_name
from integrations.salesforce.soql import build_active_users_soql, build_user_by_ids_soql

logger = logging.getLogger(__name__)

_ROLE_SOQL = "SELECT Id, Name, DeveloperName FROM UserRole"
_USER_PERMISSION_PREFIX = "UserPermissions"


def _role_name_by_id(roles: list[dict[str, Any]]) -> dict[str, str]:
    return {str(row["Id"]): str(row.get("Name") or row.get("DeveloperName") or row["Id"]) for row in roles}


def email_from_user(user: dict[str, Any]) -> str | None:
    email = user.get("Email")
    if email and str(email).strip():
        return str(email)
    username = user.get("Username")
    if username and "@" in str(username):
        return str(username)
    return None


def select_user_permission_fields(fields: list[dict[str, Any]]) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for field in fields:
        name = field.get("name")
        if not isinstance(name, str) or not name.startswith(_USER_PERMISSION_PREFIX):
            continue
        if field.get("type") != "boolean":
            continue
        try:
            validate_field_name(name)
        except ValueError:
            continue
        label = field.get("label")
        selected.append((name, label.strip() if isinstance(label, str) and label.strip() else name))
    selected.sort(key=lambda item: item[0])
    return selected


def load_user_permission_fields(sf: Salesforce) -> list[tuple[str, str]]:
    try:
        payload = sf.User.describe()
    except Exception as exc:
        logger.warning("user_permission_describe_failed error=%s", exc)
        return []
    if not isinstance(payload, dict):
        return []
    fields = payload.get("fields")
    if not isinstance(fields, list):
        return []
    return select_user_permission_fields([field for field in fields if isinstance(field, dict)])


def user_permissions_from_record(
    user: dict[str, Any],
    permission_fields: list[tuple[str, str]],
) -> dict[str, SalesforceUserPermissionFlag]:
    flags: dict[str, SalesforceUserPermissionFlag] = {}
    for name, label in permission_fields:
        value = user.get(name)
        if isinstance(value, bool):
            flags[name] = SalesforceUserPermissionFlag(label=label, enabled=value)
    return flags


def identity_row_from_user(
    user: dict[str, Any],
    *,
    connection: ConnectionRef,
    role_name_by_id: dict[str, str],
    permission_fields: list[tuple[str, str]] | None = None,
) -> AppIdentityRow:
    role_id = user.get("UserRoleId")
    role_id_str = str(role_id) if role_id else None
    extra = SalesforceAppIdentityExtra(
        role_id=role_id_str,
        role_name=role_name_by_id.get(role_id_str) if role_id_str else None,
        user_permissions=user_permissions_from_record(user, permission_fields or []),
    )
    return AppIdentityRow(
        app=SALESFORCE_APP,
        external_id=str(user["Id"]),
        name=str(user.get("Name") or user.get("Username") or user["Id"]),
        extra=extra.model_dump(),
        connection_app=connection["app"],
        connection_external_id=connection["external_id"],
    )


async def _correlate_users(users: list[dict[str, Any]]) -> None:
    rows = [
        row
        for user in users
        if (
            row := correlation_row_from_email(
                app=SALESFORCE_APP,
                app_identity_external_id=str(user["Id"]),
                email=email_from_user(user),
                display_name=str(user.get("Name") or user.get("Username") or user["Id"]),
            )
        )
        is not None
    ]
    await correlate_app_identities_by_email(rows)


async def ingest_users(
    sf: Salesforce,
    *,
    connection: ConnectionRef,
) -> dict[str, str]:
    permission_fields = load_user_permission_fields(sf)
    users = query_all(sf, build_active_users_soql(name for name, _label in permission_fields))
    roles = query_all(sf, _ROLE_SOQL)
    role_name_by_id = _role_name_by_id(roles)
    rows = [
        identity_row_from_user(
            user,
            connection=connection,
            role_name_by_id=role_name_by_id,
            permission_fields=permission_fields,
        )
        for user in users
    ]
    await merge_app_identities(rows)
    await _correlate_users(users)
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

    permission_fields = load_user_permission_fields(sf)
    users = query_all(sf, build_user_by_ids_soql(missing, (name for name, _label in permission_fields)))
    roles = query_all(sf, _ROLE_SOQL)
    role_name_by_id = _role_name_by_id(roles)
    rows = [
        identity_row_from_user(
            user,
            connection=connection,
            role_name_by_id=role_name_by_id,
            permission_fields=permission_fields,
        )
        for user in users
    ]
    if rows:
        await merge_app_identities(rows)
        await _correlate_users(users)
        logger.info("ensure_identities_for_ids added=%s", len(rows))
