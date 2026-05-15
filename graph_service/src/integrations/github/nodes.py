from __future__ import annotations

from neomodel import AsyncOne, AsyncRelationshipFrom, StringProperty

from nodes.base import BaseNode


class GithubUser(BaseNode):
    """GitHub-specific identity profile.

    Linked from an Identity node via the HAS_PROFILE relationship. Never
    instantiated or queried in isolation — always accessed through the owning
    Identity. The cardinality on the back-reference is AsyncOne because a
    GitHub profile always belongs to exactly one Identity.
    """

    github_user_id = StringProperty(unique_index=True, required=True)
    github_username = StringProperty(required=True)
    installation_id = StringProperty()

    identity = AsyncRelationshipFrom(
        "nodes.identity.Identity",
        "HAS_PROFILE",
        cardinality=AsyncOne,
    )
