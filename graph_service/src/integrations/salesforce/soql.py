"""Validated SOQL builders for dynamic Salesforce queries."""

from __future__ import annotations

from collections.abc import Iterable

from integrations.salesforce.ids import validate_salesforce_id
from integrations.salesforce.share_objects import (
    access_level_field_for_sobject,
    parent_id_field_for_sobject,
    validate_field_name,
    validate_share_object_api_name,
    validate_sobject_api_name,
)


def format_id_in_clause(ids: Iterable[str]) -> str:
    validated_ids = [validate_salesforce_id(sf_id) for sf_id in ids]
    return ", ".join(f"'{sf_id}'" for sf_id in validated_ids)


def build_user_by_ids_soql(ids: Iterable[str]) -> str:
    id_clause = format_id_in_clause(ids)
    return (
        "SELECT Id, Username, Name, ProfileId, UserRoleId, ManagerId, IsActive "
        "FROM User WHERE Id IN (" + id_clause + ")"  # nosec B608
    )


def build_group_by_ids_soql(ids: Iterable[str]) -> str:
    id_clause = format_id_in_clause(ids)
    return "SELECT Id, Name, DeveloperName, Type FROM Group WHERE Id IN (" + id_clause + ")"  # nosec B608


def escape_soql_string_literal(value: str) -> str:
    return value.replace("'", "\\'")


def build_owned_records_soql(*, sobject_type: str, name_prefix: str) -> str:
    validated_sobject = validate_sobject_api_name(sobject_type)
    escaped_prefix = escape_soql_string_literal(name_prefix)
    return (
        "SELECT Id, Name, OwnerId FROM " + validated_sobject + " WHERE Name LIKE '" + escaped_prefix + "%'"  # nosec B608
    )


def build_account_by_name_soql(*, account_name: str) -> str:
    escaped_name = escape_soql_string_literal(account_name)
    return "SELECT Id FROM Account WHERE Name = '" + escaped_name + "' LIMIT 1"  # nosec B608


def build_share_table_soql(*, share_object_name: str, target_sobject: str) -> str:
    validated_share_object = validate_share_object_api_name(share_object_name)
    validated_target = validate_sobject_api_name(target_sobject)
    parent_field = parent_id_field_for_sobject(validated_target)
    access_field = access_level_field_for_sobject(validated_target)
    validate_field_name(parent_field)
    validate_field_name(access_field)
    return (
        "SELECT Id, "  # nosec B608
        + parent_field
        + ", UserOrGroupId, RowCause, "
        + access_field
        + " FROM "
        + validated_share_object
    )
