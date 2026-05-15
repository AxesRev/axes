from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Group(BaseNode):
    """A named container of AppIdentity nodes and/or other Groups.

    Membership is expressed as an inbound MEMBER_OF edge from either an
    AppIdentity or a nested Group. Two separate relationship properties are
    required because neomodel does not support union target types.
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
    resources = AsyncRelationshipTo(
        "nodes.resource.Resource",
        "HAS_PERMISSION",
        model=HasPermissionRel,
        cardinality=AsyncZeroOrMore,
    )
