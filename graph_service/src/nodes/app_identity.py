from __future__ import annotations

from neomodel import AsyncOne, AsyncRelationshipFrom, AsyncRelationshipTo, AsyncZeroOrMore, JSONProperty, StringProperty

from nodes.base import BaseNode


class AppIdentity(BaseNode):
    """A generic per-app identity profile linked to a canonical Identity.

    ``app`` names the integration ("github", "slack", "jira", …).
    ``external_id`` is that integration's own stable identifier for this user.
    ``extra`` is a schemaless JSON blob — integrations store whatever
    app-specific fields they need there without touching the graph schema.
    """

    app = StringProperty(required=True)
    external_id = StringProperty(required=True)
    extra = JSONProperty()

    identity = AsyncRelationshipFrom(
        "nodes.identity.Identity",
        "HAS_PROFILE",
        cardinality=AsyncOne,
    )
    groups = AsyncRelationshipTo(
        "nodes.group.Group",
        "MEMBER_OF",
        cardinality=AsyncZeroOrMore,
    )

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
