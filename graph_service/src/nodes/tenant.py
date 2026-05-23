from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode


class Tenant(BaseNode):
    """Top-level organisational boundary.

    ``external_id`` (from BaseNode) is the stable identifier from the owning
    system of record when available. ``name`` is a human-readable label.
    """

    name = StringProperty(required=True)

    identities = AsyncRelationshipFrom(
        "nodes.identity.Identity",
        "BELONGS_TO",
        cardinality=AsyncZeroOrMore,
    )
    app_connections = AsyncRelationshipFrom(
        "nodes.app_connection.AppConnection",
        "BELONGS_TO",
        cardinality=AsyncZeroOrMore,
    )
