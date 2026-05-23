"""Salesforce ID validation and graph subject resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_keys.htm
KEY_PREFIX_USER = "005"
KEY_PREFIX_GROUP = "00G"

GraphSubjectKind = Literal["identity", "group"]

_SALESFORCE_ID_RE = re.compile(r"^[a-zA-Z0-9]{15,18}$")
_KEY_PREFIX_TO_KIND: dict[str, GraphSubjectKind] = {
    KEY_PREFIX_USER: "identity",
    KEY_PREFIX_GROUP: "group",
}


def validate_salesforce_id(sf_id: str) -> str:
    if not _SALESFORCE_ID_RE.fullmatch(sf_id):
        msg = f"invalid Salesforce id: {sf_id!r}"
        raise ValueError(msg)
    return sf_id


@dataclass(frozen=True, slots=True)
class GraphSubjectRef:
    kind: GraphSubjectKind
    external_id: str


def graph_subject_from_user_or_group_id(user_or_group_id: str) -> GraphSubjectRef | None:
    """Map a Salesforce UserOrGroupId/AssigneeId to a graph subject."""
    try:
        sf_id = validate_salesforce_id(user_or_group_id)
    except ValueError:
        return None
    kind = _KEY_PREFIX_TO_KIND.get(sf_id[:3])
    if kind is None:
        return None
    return GraphSubjectRef(kind=kind, external_id=sf_id)
