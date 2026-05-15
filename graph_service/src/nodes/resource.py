from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode


class Resource(BaseNode):
    """An object that access control applies to.

    ``kind`` describes the type of resource (e.g. "repository", "branch",
    "endpoint") without coupling the schema to any specific integration.
    ``uri`` is an optional stable locator that uniquely identifies the resource
    within its kind.

    Access is expressed as a typed edge from the subject to this node:
        (AppIdentity)-[:READ_ONLY | :READ_WRITE | :ADMIN]->(Resource)
    Each access level is a separate relationship type so that permission checks
    reduce to a single edge lookup with no property filtering.
    """

    name = StringProperty(required=True)
    kind = StringProperty(required=True)
    uri = StringProperty(unique_index=True)

    read_only_subjects = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "READ_ONLY",
        cardinality=AsyncZeroOrMore,
    )
    read_write_subjects = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "READ_WRITE",
        cardinality=AsyncZeroOrMore,
    )
    admin_subjects = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "ADMIN",
        cardinality=AsyncZeroOrMore,
    )

    read_only_profiles = AsyncRelationshipFrom(
        "nodes.profile.Profile",
        "READ_ONLY",
        cardinality=AsyncZeroOrMore,
    )
    read_write_profiles = AsyncRelationshipFrom(
        "nodes.profile.Profile",
        "READ_WRITE",
        cardinality=AsyncZeroOrMore,
    )
    admin_profiles = AsyncRelationshipFrom(
        "nodes.profile.Profile",
        "ADMIN",
        cardinality=AsyncZeroOrMore,
    )
