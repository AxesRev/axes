from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode


class Tenant(BaseNode):
    """Top-level organisational boundary.

    ``external_id`` is the stable identifier from the owning system of record.
    ``name`` is a human-readable label that may change over time.
    """

    external_id = StringProperty(required=True, unique_index=True)
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
