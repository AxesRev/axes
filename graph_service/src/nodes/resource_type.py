from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class ResourceType(BaseNode):
    """A catalog type that Resource instances belong to.

    Types are ingested per AppConnection even when the connection has no
    instances yet (e.g. a Salesforce SObject with zero records, or GitHub
    ``repository`` before any repos exist). ``name`` is the type's API name
    (``Campaign``, ``repository``). ``external_id`` is unique per connection.

    Type-level access is a HAS_PERMISSION edge onto this node. Instance-level
    access points at the Resource instead.
    """

    name = StringProperty(required=True)

    instances = AsyncRelationshipFrom(
        "nodes.resource.Resource",
        "INSTANCE_OF",
        cardinality=AsyncZeroOrMore,
    )
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
