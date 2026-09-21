"""Validated SOQL builders for dynamic Salesforce queries."""

from __future__ import annotations

from collections.abc import Iterable

from integrations.salesforce.ids import validate_salesforce_id
from integrations.salesforce.share_objects import (
    validate_field_name,
    validate_share_object_api_name,
)

_USER_BASE_FIELDS = (
    "Id",
    "Username",
    "Name",
    "Email",
    "ProfileId",
    "UserRoleId",
    "ManagerId",
    "IsActive",
)


def format_id_in_clause(ids: Iterable[str]) -> str:
    validated_ids = [validate_salesforce_id(sf_id) for sf_id in ids]
    return ", ".join(f"'{sf_id}'" for sf_id in validated_ids)


def user_select_clause(permission_fields: Iterable[str] = ()) -> str:
    fields = list(_USER_BASE_FIELDS)
    for name in permission_fields:
        validated = validate_field_name(name)
        if not validated.startswith("UserPermissions"):
            msg = f"not a user permission field: {name!r}"
            raise ValueError(msg)
        fields.append(validated)
    return ", ".join(fields)


def build_active_users_soql(permission_fields: Iterable[str] = ()) -> str:
    return "SELECT " + user_select_clause(permission_fields) + " FROM User WHERE IsActive = true"  # nosec B608


def build_user_by_ids_soql(ids: Iterable[str], permission_fields: Iterable[str] = ()) -> str:
    id_clause = format_id_in_clause(ids)
    return (
        "SELECT " + user_select_clause(permission_fields) + " FROM User WHERE Id IN (" + id_clause + ")"  # nosec B608
    )


def build_group_by_ids_soql(ids: Iterable[str]) -> str:
    id_clause = format_id_in_clause(ids)
    return "SELECT Id, Name, DeveloperName, Type FROM Group WHERE Id IN (" + id_clause + ")"  # nosec B608


def build_share_table_soql(
    *,
    share_object_name: str,
    parent_id_field: str,
    access_level_field: str,
) -> str:
    validated_share_object = validate_share_object_api_name(share_object_name)
    parent_field = validate_field_name(parent_id_field)
    access_field = validate_field_name(access_level_field)
    return (
        "SELECT Id, "  # nosec B608
        + parent_field
        + ", UserOrGroupId, RowCause, "
        + access_field
        + " FROM "
        + validated_share_object
    )
