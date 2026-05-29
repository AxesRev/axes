from __future__ import annotations

from neomodel import AsyncStructuredNode, DateTimeProperty, StringProperty, UniqueIdProperty


class BaseNode(AsyncStructuredNode):
    """Abstract base for all graph nodes.

    Subclass this instead of AsyncStructuredNode directly. Setting
    __abstract_node__ = True prevents neomodel from registering this class as
    a concrete label in the Neo4j schema.

    ``app`` and ``external_id`` are optional integration identifiers. Set them
    when a node maps to a concrete object in an external system. Leave them
    unset for synthetic or type-level nodes (e.g. a Salesforce SObject name
    without a persisted external key). Integrations validate required IDs at
    ingest time where needed.
    """

    __abstract_node__ = True

    app = StringProperty()
    external_id = StringProperty()
    uid = UniqueIdProperty()
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
