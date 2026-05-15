from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Resource(BaseNode):
    """An object that access control applies to.

    ``kind`` describes the type of resource without coupling the schema to any
    specific integration. ``uri`` is an optional stable locator that uniquely
    identifies the resource within its kind.

    Access is expressed as a HAS_PERMISSION edge from the subject to this node.
    The permission type is carried as a property on the edge itself so that new
    permission types require no schema change.
    """

    name = StringProperty(required=True)
    kind = StringProperty(required=True)
    uri = StringProperty(unique_index=True)

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
