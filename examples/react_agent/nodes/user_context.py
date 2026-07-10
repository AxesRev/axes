"""Load per-app user context for the apps selected for this request."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import State
from examples.react_agent.user_context_models import UserContextData
from examples.react_agent.user_context_service import fetch_user_context_for_app

logger = logging.getLogger(__name__)


def _resolve_identity_for_app(*, app: str, runtime: Runtime[Context]) -> tuple[str | None, str | None]:
    if app == "github":
        user_id = runtime.context.github_user_id.strip()
        return (user_id or None, None)
    if app == "salesforce":
        email = runtime.context.github_email.strip()
        return (None, email or None)
    return (None, None)


async def load_user_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Fetch graph-backed user context for each selected app."""
    if not state.selected_apps:
        logger.info("load_user_context: no selected apps")
        return {"user_contexts": []}

    contexts: list[UserContextData] = []
    for app in state.selected_apps:
        user_id, email = _resolve_identity_for_app(app=app, runtime=runtime)
        if user_id is None and email is None:
            logger.info("load_user_context: skipped app=%s — no identity hints", app)
            continue

        try:
            user_context = await fetch_user_context_for_app(app=app, user_id=user_id, email=email)
        except RuntimeError:
            logger.info("load_user_context: skipped app=%s — Neo4j MCP not configured", app)
            continue

        if user_context is None:
            logger.info("load_user_context: no graph identity for app=%s", app)
            continue

        contexts.append(user_context)
        logger.info(
            "load_user_context: loaded app=%s user=%s groups=%d permissions=%d",
            user_context.app,
            user_context.user_name,
            len(user_context.groups),
            len(user_context.permissions),
        )

    return {"user_contexts": contexts}
