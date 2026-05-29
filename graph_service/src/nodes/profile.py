from __future__ import annotations

from neomodel import (
    AsyncRelationshipFrom,
    AsyncRelationshipTo,
    AsyncZeroOrMore,
    AsyncZeroOrOne,
    JSONProperty,
    StringProperty,
)

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Profile(BaseNode):
    """A reusable bundle of access rights that can be assigned to subjects.

    ``app`` and ``external_id`` (from BaseNode) identify the profile in the
    source system when available (e.g. Salesforce Profile or PermissionSet Id).

    AppIdentity and Group nodes link via ASSIGNED_PROFILE when a bundle is
    assigned directly to them. Profile nodes may belong to another Profile via
    MEMBER_OF (e.g. permission sets grouped into a permission set group).

    ASSIGNED_PROFILE is kept distinct from HAS_PROFILE (Identity → AppIdentity).
    """

    name = StringProperty(required=True)
    description = StringProperty()
    extra = JSONProperty()

    permitted_resources = AsyncRelationshipTo(
        "nodes.resource.Resource",
        "HAS_PERMISSION",
        model=HasPermissionRel,
        cardinality=AsyncZeroOrMore,
    )
    permitted_groups = AsyncRelationshipTo(
        "nodes.group.Group",
        "HAS_PERMISSION",
        model=HasPermissionRel,
        cardinality=AsyncZeroOrMore,
    )
    assigned_identities = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "ASSIGNED_PROFILE",
        cardinality=AsyncZeroOrMore,
    )
    assigned_groups = AsyncRelationshipFrom(
        "nodes.group.Group",
        "ASSIGNED_PROFILE",
        cardinality=AsyncZeroOrMore,
    )
    groups = AsyncRelationshipTo(
        "nodes.profile.Profile",
        "MEMBER_OF",
        cardinality=AsyncZeroOrMore,
    )
    profile_members = AsyncRelationshipFrom(
        "nodes.profile.Profile",
        "MEMBER_OF",
        cardinality=AsyncZeroOrMore,
    )
    connection = AsyncRelationshipTo(
        "nodes.app_connection.AppConnection",
        "BELONGS_TO",
        cardinality=AsyncZeroOrOne,
    )
