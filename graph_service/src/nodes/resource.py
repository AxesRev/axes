from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Resource(BaseNode):
    """A concrete instance that access control applies to.

    ``external_id`` (from BaseNode) is the instance id in the external system
    (Salesforce record id, GitHub repo id). ``name`` and ``uri`` are display
    fields that may change. ``kind`` denormalizes the ResourceType name
    (``Campaign``, ``repository``). The canonical type link is INSTANCE_OF.

    Instance-level access is a HAS_PERMISSION edge onto this node. Type-level
    access (create Campaigns, create repositories) points at ResourceType.
    """

    name = StringProperty(required=True)
    kind = StringProperty(required=True)
    uri = StringProperty()

    resource_type = AsyncRelationshipTo(
        "nodes.resource_type.ResourceType",
        "INSTANCE_OF",
        cardinality=AsyncZeroOrOne,
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
