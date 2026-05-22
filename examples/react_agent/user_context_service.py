"""Fetch user context from the Neo4j graph via MCP."""

from __future__ import annotations

import logging

from examples.react_agent.nodes.tools import read_neo4j_cypher
from examples.react_agent.user_context_models import UserContextData, build_user_context

logger = logging.getLogger(__name__)

_USER_CONTEXT_QUERY = """
MATCH (u:AppIdentity {app: $app, external_id: $user_id})
OPTIONAL MATCH (u)-[:MEMBER_OF]->(g:Group)
OPTIONAL MATCH (u)-[p:HAS_PERMISSION]->(target)
WHERE target:Resource OR target:Group
OPTIONAL MATCH (target)-[:BELONGS_TO]->(owner:AppConnection)
RETURN u.app AS app,
       u.external_id AS user_id,
       u.name AS user_name,
       collect(DISTINCT {
           external_id: g.external_id,
           name: g.name,
           description: g.description
       }) AS groups,
       collect(DISTINCT {
           permission: p.permission,
           target_kind: head([label IN labels(target) WHERE label IN ['Resource', 'Group']]),
           target_name: target.name,
           target_external_id: target.external_id,
           owner_name: CASE WHEN target:Resource THEN owner.name ELSE null END,
           owner_external_id: CASE WHEN target:Resource THEN owner.external_id ELSE null END
       }) AS permissions
"""


async def fetch_user_context(*, app: str, user_id: str) -> UserContextData | None:
    """Load user, group, and permission context via read_neo4j_cypher on Neo4j MCP."""
    rows = await read_neo4j_cypher(_USER_CONTEXT_QUERY, {"app": app, "user_id": user_id})
    if not rows:
        logger.info("fetch_user_context: no AppIdentity found app=%s user_id=%s", app, user_id)
        return None

    user_context = build_user_context(rows[0])
    logger.info(
        "fetch_user_context: loaded app=%s user_id=%s groups=%d permissions=%d",
        user_context.app,
        user_context.user_id,
        len(user_context.groups),
        len(user_context.permissions),
    )
    return user_context
