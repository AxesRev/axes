from __future__ import annotations

from neomodel import AsyncRelationshipFrom, AsyncZeroOrMore, StringProperty

from nodes.base import BaseNode


class Tenant(BaseNode):
    """Top-level organisational boundary.

    A Tenant owns a set of app-agnostic Identity nodes. All app-specific
    data (AppConnection, AppIdentity, Resource, Group, Profile) hangs off
    those Identities rather than the Tenant directly, keeping the Tenant
    layer free of integration concerns.
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
