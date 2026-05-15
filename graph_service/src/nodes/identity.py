from __future__ import annotations

from neomodel import AsyncRelationshipTo, AsyncZeroOrOne, StringProperty

from nodes.base import BaseNode

_IDENTITY_KINDS: dict[str, str] = {
    "human": "Human",
    "service_account": "Service Account",
    "bot": "Bot",
    "api_key": "API Key",
}


class Identity(BaseNode):
    """A canonical identity anchor, independent of any external system.

    The ``kind`` field discriminates between identity subtypes without
    requiring subclassing (which breaks neomodel queryset traversals).
    App-specific data — GitHub username, Slack user ID, etc. — lives in
    dedicated profile nodes linked via HAS_PROFILE.
    """

    name = StringProperty(required=True)
    kind = StringProperty(choices=_IDENTITY_KINDS, required=True)

    github_profile = AsyncRelationshipTo(
        "integrations.github.nodes.GithubUser",
        "HAS_PROFILE",
        cardinality=AsyncZeroOrOne,
    )
