"""Node that loads tenant agent context from PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.runtime import Runtime

from aegra_api.core.orm import get_session
from examples.react_agent.context import Context
from examples.react_agent.state import State
from tenant.agent_context_service import get_agent_context_for_tenant

logger = logging.getLogger(__name__)


async def load_tenant_agent_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Fetch editable tenant context text for access-request evaluation."""
    tenant_id = runtime.context.tenant_id.strip()
    if not tenant_id:
        logger.info("load_tenant_agent_context: skipped — tenant_id not set")
        return {}

    content = ""
    async for session in get_session():
        row = await get_agent_context_for_tenant(tenant_id=tenant_id, session=session)
        if row is not None:
            content = row.content
        break

    if not content.strip():
        logger.info("load_tenant_agent_context: no content for tenant_id=%s", tenant_id)
        return {"tenant_agent_context": ""}

    logger.info("load_tenant_agent_context: loaded %d characters for tenant_id=%s", len(content), tenant_id)
    return {"tenant_agent_context": content}
