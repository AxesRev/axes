"""Read and write per-tenant agent context text."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tenant.models import TenantAgentContext

AGENT_CONTEXT_MAX_LENGTH = 100_000


async def get_agent_context_for_tenant(
    *,
    tenant_id: str,
    session: AsyncSession,
) -> TenantAgentContext | None:
    """Return the agent context row for a tenant, if one exists."""
    result = await session.execute(select(TenantAgentContext).where(TenantAgentContext.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def upsert_agent_context_for_tenant(
    *,
    tenant_id: str,
    content: str,
    session: AsyncSession,
) -> TenantAgentContext:
    """Create or update the agent context row for a tenant."""
    if len(content) > AGENT_CONTEXT_MAX_LENGTH:
        raise ValueError(f"content must be at most {AGENT_CONTEXT_MAX_LENGTH} characters")

    existing = await get_agent_context_for_tenant(tenant_id=tenant_id, session=session)
    now = datetime.now(UTC)
    if existing is not None:
        existing.content = content
        existing.updated_at = now
        await session.commit()
        await session.refresh(existing)
        return existing

    row = TenantAgentContext(tenant_id=tenant_id, content=content, updated_at=now)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
