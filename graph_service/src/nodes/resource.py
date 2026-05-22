from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Resource(BaseNode):
    """An object that access control applies to.

    ``external_id`` is the stable identifier from the external system.
    ``name`` and ``uri`` are display/locator fields that may change (e.g. on rename).
    ``kind`` describes the type of resource without coupling the schema to any
    specific integration.

    Access is expressed as a HAS_PERMISSION edge from the subject to this node.
    The permission type is carried as a property on the edge itself so that new
    permission types require no schema change.
    """

    external_id = StringProperty(required=True, unique_index=True)
    name = StringProperty(required=True)
    kind = StringProperty(required=True)
    uri = StringProperty()

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
