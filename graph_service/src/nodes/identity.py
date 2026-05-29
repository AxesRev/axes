from __future__ import annotations

from neomodel import AsyncRelationshipTo, AsyncZeroOrMore, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode

_IDENTITY_KINDS: dict[str, str] = {
    "human": "Human",
    "service_account": "Service Account",
    "bot": "Bot",
    "api_key": "API Key",
}


class Identity(BaseNode):
    """A canonical identity anchor, independent of any external system.

    ``app`` and ``external_id`` (from BaseNode) may be set when this identity
    is anchored to an external record; otherwise leave them unset.

    The ``kind`` field discriminates between identity subtypes without
    requiring subclassing (which breaks neomodel queryset traversals).
    App-specific data — GitHub username, Slack user ID, etc. — lives in
    dedicated profile nodes linked via HAS_PROFILE.
    """

    name = StringProperty(required=True)
    kind = StringProperty(choices=_IDENTITY_KINDS, required=True)

    app_profiles = AsyncRelationshipTo(
        "nodes.app_identity.AppIdentity",
        "HAS_PROFILE",
        cardinality=AsyncZeroOrMore,
    )
    tenant = AsyncRelationshipTo(
        "nodes.tenant.Tenant",
        "BELONGS_TO",
        cardinality=AsyncZeroOrOne,
    )
