from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode


class Profile(BaseNode):
    """A reusable bundle of access rights that can be assigned to subjects.

    Permissions are modelled as typed edges to Resource nodes — the same
    READ_ONLY / READ_WRITE / ADMIN relationship types used for direct subject
    access — so a single Cypher traversal can resolve permissions regardless
    of whether they come from a direct edge or an assigned Profile.

    Both AppIdentity and Group nodes can hold an ASSIGNED_PROFILE edge to
    this node. ASSIGNED_PROFILE is kept distinct from HAS_PROFILE
    (Identity → AppIdentity) to avoid ambiguity in the graph.
    """

    name = StringProperty(required=True)
    description = StringProperty()

    read_only_resources = AsyncRelationshipTo(
        "nodes.resource.Resource",
        "READ_ONLY",
        cardinality=AsyncZeroOrMore,
    )
    read_write_resources = AsyncRelationshipTo(
        "nodes.resource.Resource",
        "READ_WRITE",
        cardinality=AsyncZeroOrMore,
    )
    admin_resources = AsyncRelationshipTo(
        "nodes.resource.Resource",
        "ADMIN",
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
