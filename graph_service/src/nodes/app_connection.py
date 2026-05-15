from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, JSONProperty, StringProperty

from nodes.base import BaseNode


class AppConnection(BaseNode):
    """A workspace or tenant context within an external app.

    ``app`` identifies the integration ("github", "slack", …).
    ``external_id`` is the app's own stable identifier for this workspace.
    ``extra`` is a schemaless JSON blob for any app-specific fields that do
    not belong in the common schema.

    All nodes that are scoped to this workspace — AppIdentity, Resource,
    Group, Profile — point here via a BELONGS_TO edge.
    """

    app = StringProperty(required=True)
    external_id = StringProperty(required=True)
    name = StringProperty(required=True)
    extra = JSONProperty()

    identities = AsyncRelationshipFrom(
        "nodes.app_identity.AppIdentity",
        "BELONGS_TO",
        cardinality=AsyncZeroOrMore,
    )
    resources = AsyncRelationshipFrom(
        "nodes.resource.Resource",
        "BELONGS_TO",
        cardinality=AsyncZeroOrMore,
    )
    groups = AsyncRelationshipFrom(
        "nodes.group.Group",
        "BELONGS_TO",
        cardinality=AsyncZeroOrMore,
    )
    profiles = AsyncRelationshipFrom(
        "nodes.profile.Profile",
        "BELONGS_TO",
        cardinality=AsyncZeroOrMore,
    )
