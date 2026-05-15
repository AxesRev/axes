from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Group(BaseNode):
    """A named container of AppIdentity nodes and/or other Groups.

    Group acts as both a subject (can hold HAS_PERMISSION edges to Resource
    and other Group nodes) and a target (subjects can hold HAS_PERMISSION
    edges pointing at this Group).
    """

    name = StringProperty(required=True)
    description = StringProperty()

    identity_members = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "MEMBER_OF",
        cardinality=AsyncZeroOrMore,
    )
    group_members = AsyncRelationshipFrom(
        "nodes.group.Group",
        "MEMBER_OF",
        cardinality=AsyncZeroOrMore,
    )
    profiles = AsyncRelationshipTo(
        "nodes.profile.Profile",
        "ASSIGNED_PROFILE",
        cardinality=AsyncZeroOrMore,
    )

    # Subject side — permissions this group holds
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

    # Target side — who holds permissions on this group
    app_identity_permissions = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "HAS_PERMISSION",
        model=HasPermissionRel,
        cardinality=AsyncZeroOrMore,
    )
    group_permissions = AsyncRelationshipFrom(
        "nodes.group.Group",
        "HAS_PERMISSION",
        model=HasPermissionRel,
        cardinality=AsyncZeroOrMore,
    )
    profile_permissions = AsyncRelationshipFrom(
        "nodes.profile.Profile",
        "HAS_PERMISSION",
        model=HasPermissionRel,
        cardinality=AsyncZeroOrMore,
    )
    connection = AsyncRelationshipTo(
        "nodes.app_connection.AppConnection",
        "BELONGS_TO",
        cardinality=AsyncZeroOrOne,
    )
