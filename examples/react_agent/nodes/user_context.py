"""Node that loads user context from the Neo4j MCP graph service."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State
from examples.react_agent.user_context_service import fetch_user_context

logger = logging.getLogger(__name__)

_DEFAULT_APP = "github"


async def load_user_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Fetch the requesting user's graph context via Neo4j MCP and store it on state."""
    user_id = runtime.context.github_user_id.strip()
    if not user_id:
        logger.info("load_user_context: skipped — github_user_id not set")
        return {}

    try:
        user_context = await fetch_user_context(app=_DEFAULT_APP, user_id=user_id)
    except RuntimeError:
        logger.info("load_user_context: skipped — Neo4j MCP not configured")
        return {}

    if user_context is None:
        logger.info("load_user_context: no graph identity for app=%s user_id=%s", _DEFAULT_APP, user_id)
        return {}

    logger.info(
        "load_user_context: loaded user=%s groups=%d permissions=%d",
        user_context.user_name,
        len(user_context.groups),
        len(user_context.permissions),
    )
    return {"user_context": user_context}
