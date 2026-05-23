"""Validated SOQL builders for dynamic Salesforce queries."""

from __future__ import annotations

import re
from collections.abc import Iterable

_SALESFORCE_ID_RE = re.compile(r"^[a-zA-Z0-9]{15,18}$")
_SOBJECT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(__c)?$")
_SHARE_OBJECT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(__Share|Share)$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

_OBJECT_ACCESS_FIELD: dict[str, str] = {
    "Account": "AccountAccessLevel",
    "Case": "CaseAccessLevel",
    "Opportunity": "OpportunityAccessLevel",
    "Contact": "ContactAccessLevel",
    "Lead": "LeadAccessLevel",
}


def validate_salesforce_id(sf_id: str) -> str:
    if not _SALESFORCE_ID_RE.fullmatch(sf_id):
        msg = f"invalid Salesforce id: {sf_id!r}"
        raise ValueError(msg)
    return sf_id


def validate_sobject_api_name(name: str) -> str:
    if not _SOBJECT_NAME_RE.fullmatch(name):
        msg = f"invalid SObject api name: {name!r}"
        raise ValueError(msg)
    return name


def validate_share_object_api_name(name: str) -> str:
    if not _SHARE_OBJECT_RE.fullmatch(name):
        msg = f"invalid Share object api name: {name!r}"
        raise ValueError(msg)
    return name


def validate_field_name(name: str) -> str:
    if not _FIELD_NAME_RE.fullmatch(name):
        msg = f"invalid field name: {name!r}"
        raise ValueError(msg)
    return name


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


def build_share_table_soql(*, share_object_name: str, target_sobject: str) -> str:
    validated_share_object = validate_share_object_api_name(share_object_name)
    validated_target = validate_sobject_api_name(target_sobject)
    if validated_target.endswith("__c"):
        parent_field = "ParentId"
    else:
        parent_field = f"{validated_target}Id"
    selected_access_field = _OBJECT_ACCESS_FIELD.get(validated_target, "AccessLevel")
    validate_field_name(parent_field)
    validate_field_name(selected_access_field)
    return (
        "SELECT Id, "  # nosec B608
        + parent_field
        + ", UserOrGroupId, RowCause, "
        + selected_access_field
        + " FROM "
        + validated_share_object
    )
