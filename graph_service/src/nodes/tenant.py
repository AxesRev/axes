from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode


class Tenant(BaseNode):
    """Top-level organisational boundary.

    ``external_id`` (from BaseNode) is the Postgres ``tenants.id`` for ingested
    workspaces. ``name`` is the tenant display name from the metadata DB.
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
