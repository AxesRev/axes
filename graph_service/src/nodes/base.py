from __future__ import annotations

from neomodel import AsyncStructuredNode, DateTimeProperty, UniqueIdProperty


class BaseNode(AsyncStructuredNode):
    """Abstract base for all graph nodes.

    Subclass this instead of AsyncStructuredNode directly. Setting
    __abstract_node__ = True prevents neomodel from registering this class as
    a concrete label in the Neo4j schema.
    """

    __abstract_node__ = True

    uid = UniqueIdProperty()
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
