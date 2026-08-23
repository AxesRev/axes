"""Share object naming, discovery, and Share-row normalization."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from simple_salesforce import Salesforce

from integrations.salesforce.client import describe_global, describe_sobject_field_names
from integrations.salesforce.ids import GraphSubjectRef, graph_subject_from_user_or_group_id

logger = logging.getLogger(__name__)

_SOBJECT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(__c)?$")
_SHARE_OBJECT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(__Share|Share)$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

ACCESS_LEVEL_FIELD_BY_SOBJECT: dict[str, str] = {
    "Account": "AccountAccessLevel",
    "Case": "CaseAccessLevel",
    "Opportunity": "OpportunityAccessLevel",
    "Contact": "ContactAccessLevel",
    "Lead": "LeadAccessLevel",
}

ALLOWED_SHARE_ROW_CAUSES = frozenset(
    {
        "Owner",
        "Manual",
        "Rule",
        "Team",
        "ImplicitChild",
        "ImplicitParent",
        "AssociatedRecord",
        "ManualUserTeam",
        "ManualGroupTeam",
        "Territory",
        "TerritoryManual",
        "TerritoryRule",
    }
)

_SHARE_ACCESS_LEVEL_MAP = {
    "Read": "read",
    "Edit": "edit",
    "All": "all",
}


@dataclass(frozen=True, slots=True)
class NormalizedShareAccess:
    record_id: str
    subject: GraphSubjectRef
    row_cause: str
    access_level: str


@dataclass(frozen=True, slots=True)
class ShareTableShape:
    share_object_name: str
    target_sobject: str
    parent_id_field: str
    access_level_field: str


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


def share_object_for_sobject(sobject_name: str) -> str:
    if sobject_name.endswith("__c"):
        return f"{sobject_name[:-3]}__Share"
    return f"{sobject_name}Share"


def sobject_for_share_object(share_object_name: str) -> str | None:
    if share_object_name.endswith("__Share"):
        return share_object_name[: -len("__Share")] + "__c"
    if share_object_name.endswith("Share"):
        return share_object_name[: -len("Share")]
    return None


def parent_id_field_for_sobject(sobject_name: str) -> str:
    if sobject_name.endswith("__c"):
        return "ParentId"
    return f"{sobject_name}Id"


def access_level_field_for_sobject(sobject_name: str) -> str:
    if sobject_name.endswith("__c"):
        return "AccessLevel"
    return ACCESS_LEVEL_FIELD_BY_SOBJECT.get(sobject_name, f"{sobject_name}AccessLevel")


def resolve_share_table_shape(
    *,
    share_object_name: str,
    target_sobject: str,
    field_names: set[str],
) -> ShareTableShape | None:
    """Pick parent and access fields that actually exist on a Share table."""
    if "UserOrGroupId" not in field_names or "RowCause" not in field_names:
        return None

    guessed_parent = parent_id_field_for_sobject(target_sobject)
    if guessed_parent in field_names:
        parent_id_field = guessed_parent
    elif "ParentId" in field_names:
        parent_id_field = "ParentId"
    else:
        return None

    named_access = f"{target_sobject}AccessLevel"
    mapped_access = ACCESS_LEVEL_FIELD_BY_SOBJECT.get(target_sobject)
    if named_access in field_names:
        access_level_field = named_access
    elif mapped_access and mapped_access in field_names:
        access_level_field = mapped_access
    elif "AccessLevel" in field_names:
        access_level_field = "AccessLevel"
    else:
        return None

    return ShareTableShape(
        share_object_name=share_object_name,
        target_sobject=target_sobject,
        parent_id_field=parent_id_field,
        access_level_field=access_level_field,
    )


def describe_share_table(
    sf: Salesforce,
    *,
    share_object_name: str,
    target_sobject: str,
) -> ShareTableShape | None:
    field_names = describe_sobject_field_names(sf, share_object_name)
    if field_names is None:
        return None
    return resolve_share_table_shape(
        share_object_name=share_object_name,
        target_sobject=target_sobject,
        field_names=field_names,
    )


def normalize_share_access_level(access_level: object | None) -> str:
    if not access_level:
        return "read"
    raw = str(access_level)
    return _SHARE_ACCESS_LEVEL_MAP.get(raw, raw.lower())


def normalize_share_access(
    row: Mapping[str, Any],
    *,
    target_sobject: str,
    parent_id_field: str | None = None,
    access_level_field: str | None = None,
) -> NormalizedShareAccess | None:
    """Normalize a Salesforce Share row into graph-ready record access."""
    subject = graph_subject_from_user_or_group_id(str(row.get("UserOrGroupId") or ""))
    if subject is None:
        return None

    row_cause = str(row.get("RowCause") or "")
    if row_cause not in ALLOWED_SHARE_ROW_CAUSES:
        return None

    parent_field = parent_id_field or parent_id_field_for_sobject(target_sobject)
    record_id = row.get(parent_field) or row.get("ParentId")
    if not record_id:
        return None

    access_field = access_level_field or access_level_field_for_sobject(target_sobject)
    access_value = row.get(access_field)
    if access_value is None:
        access_value = row.get("AccessLevel")
    return NormalizedShareAccess(
        record_id=str(record_id),
        subject=subject,
        row_cause=row_cause,
        access_level=normalize_share_access_level(access_value),
    )


def _queryable_share_object_names(sf: Salesforce) -> set[str]:
    return {
        str(summary["name"])
        for summary in describe_global(sf)
        if isinstance(summary.get("name"), str) and summary.get("queryable") and str(summary["name"]).endswith("Share")
    }


def discover_share_pairs(
    sf: Salesforce,
    *,
    allowlist: frozenset[str],
) -> list[tuple[str, str]]:
    """Return queryable (share_object_api_name, target_sobject_api_name) pairs."""
    if allowlist:
        return _pairs_from_allowlist(allowlist)

    queryable = _queryable_share_object_names(sf)
    return _pairs_from_queryable_share_objects(queryable)


def _pairs_from_allowlist(allowlist: frozenset[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for share_name in sorted(allowlist):
        target = sobject_for_share_object(share_name)
        if target is None:
            logger.warning("share_allowlist_invalid name=%s", share_name)
            continue
        pairs.append((share_name, target))
    return pairs


def _pairs_from_queryable_share_objects(queryable: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for share_name in sorted(queryable):
        target = sobject_for_share_object(share_name)
        if target is not None:
            pairs.append((share_name, target))
    return pairs
