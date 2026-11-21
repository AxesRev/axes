"""Fetch user context from the tenant's access graph."""

from __future__ import annotations

import logging

from examples.react_agent.graph_db import read_graph
from examples.react_agent.user_context_models import UserContextData, build_user_context

logger = logging.getLogger(__name__)

_USER_CONTEXT_GRAPH_TAIL = """
OPTIONAL MATCH (u)-[:MEMBER_OF]->(g:Group)
OPTIONAL MATCH (u)-[p:HAS_PERMISSION]->(target)
WHERE target:Resource OR target:ResourceType OR target:Group
OPTIONAL MATCH (target)-[:BELONGS_TO]->(owner:AppConnection)
OPTIONAL MATCH (u)-[:ASSIGNED_PROFILE]->(pr:Profile)
RETURN u.app AS app,
       u.external_id AS user_id,
       u.name AS user_name,
       u.extra AS extra,
       collect(DISTINCT {
           external_id: g.external_id,
           name: g.name,
           description: g.description
       }) AS groups,
       collect(DISTINCT {
           permission: p.permission,
           target_kind: CASE
               WHEN target:ResourceType THEN 'resource_type'
               WHEN target:Resource THEN 'resource'
               WHEN target:Group THEN 'group'
               ELSE null
           END,
           target_name: target.name,
           target_external_id: target.external_id,
           owner_name: CASE WHEN target:Resource OR target:ResourceType THEN owner.name ELSE null END,
           owner_external_id: CASE WHEN target:Resource OR target:ResourceType THEN owner.external_id ELSE null END
       }) AS permissions,
       collect(DISTINCT {
           external_id: pr.external_id,
           name: pr.name,
           description: pr.description,
           extra: pr.extra
       }) AS profiles
"""

_USER_CONTEXT_QUERY = (
    """
MATCH (u:AppIdentity {app: $app, external_id: $user_id})
"""
    + _USER_CONTEXT_GRAPH_TAIL
)

_USER_CONTEXT_BY_EMAIL_QUERY = (
    """
MATCH (i:Identity {external_id: $email})-[:HAS_PROFILE]->(u:AppIdentity {app: $app})
"""
    + _USER_CONTEXT_GRAPH_TAIL
)


async def fetch_user_context(*, tenant_id: str, app: str, user_id: str) -> UserContextData | None:
    """Load user, group, profile, and permission context from the tenant graph."""
    rows = await read_graph(tenant_id, _USER_CONTEXT_QUERY, {"app": app, "user_id": user_id})
    if not rows:
        logger.info("fetch_user_context: no AppIdentity found app=%s user_id=%s", app, user_id)
        return None

    user_context = build_user_context(rows[0])
    logger.info(
        "fetch_user_context: loaded app=%s user_id=%s groups=%d profiles=%d permissions=%d",
        user_context.app,
        user_context.user_id,
        len(user_context.groups),
        len(user_context.profiles),
        len(user_context.permissions),
    )
    return user_context


async def fetch_user_context_by_email(*, tenant_id: str, app: str, email: str) -> UserContextData | None:
    """Load user context when the app identity is linked to a canonical Identity email."""
    normalized_email = email.strip().lower()
    if not normalized_email:
        return None

    rows = await read_graph(tenant_id, _USER_CONTEXT_BY_EMAIL_QUERY, {"app": app, "email": normalized_email})
    if not rows:
        logger.info("fetch_user_context_by_email: no AppIdentity found app=%s email=%s", app, normalized_email)
        return None

    user_context = build_user_context(rows[0])
    logger.info(
        "fetch_user_context_by_email: loaded app=%s user_id=%s groups=%d profiles=%d permissions=%d",
        user_context.app,
        user_context.user_id,
        len(user_context.groups),
        len(user_context.profiles),
        len(user_context.permissions),
    )
    return user_context


async def fetch_user_context_for_app(
    *,
    tenant_id: str,
    app: str,
    user_id: str | None = None,
    email: str | None = None,
) -> UserContextData | None:
    """Resolve user context for an app using an external id and/or linked email."""
    if user_id:
        return await fetch_user_context(tenant_id=tenant_id, app=app, user_id=user_id)
    if email:
        return await fetch_user_context_by_email(tenant_id=tenant_id, app=app, email=email)
    return None
