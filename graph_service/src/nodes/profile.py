from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode
from nodes.relationships import HasPermissionRel


class Profile(BaseNode):
    """A reusable bundle of access rights that can be assigned to subjects.

    Both AppIdentity and Group nodes can hold an ASSIGNED_PROFILE edge to
    this node. ASSIGNED_PROFILE is kept distinct from HAS_PROFILE
    (Identity → AppIdentity) to avoid ambiguity in the graph.
    """

    name = StringProperty(required=True)
    description = StringProperty()

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
    connection = AsyncRelationshipTo(
        "nodes.app_connection.AppConnection",
        "BELONGS_TO",
        cardinality=AsyncZeroOrOne,
    )
