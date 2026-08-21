"""Tenant dashboard use-cases. Called from the Lambda handler, not FastAPI."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import AppIntegration, TenantAgentContext
from tenants.errors import HttpError
from tenants.service import tenant_from_claims

AGENT_CONTEXT_MAX_LENGTH = 100_000


def _tenant_payload(tenant_id: str, name: str, email: str | None) -> dict[str, object]:
    return {"id": tenant_id, "name": name, "email": email}


async def get_my_tenant(*, claims: dict[str, object], session: AsyncSession) -> dict[str, object]:
    try:
        tenant = await tenant_from_claims(claims=claims, session=session)
    except ValueError as error:
        raise HttpError(401, str(error)) from error
    return _tenant_payload(tenant.id, tenant.name, tenant.email)


async def get_my_integrations(*, claims: dict[str, object], session: AsyncSession) -> list[dict[str, object]]:
    try:
        tenant = await tenant_from_claims(claims=claims, session=session)
    except ValueError as error:
        raise HttpError(401, str(error)) from error
    result = await session.execute(
        select(AppIntegration).where(AppIntegration.tenant_id == tenant.id).order_by(AppIntegration.app_name),
    )
    return [
        {"id": integration.id, "app_name": integration.app_name, "config": integration.config}
        for integration in result.scalars().all()
    ]


async def get_my_agent_context(*, claims: dict[str, object], session: AsyncSession) -> dict[str, object]:
    try:
        tenant = await tenant_from_claims(claims=claims, session=session)
    except ValueError as error:
        raise HttpError(401, str(error)) from error
    result = await session.execute(
        select(TenantAgentContext).where(TenantAgentContext.tenant_id == tenant.id),
    )
    context = result.scalar_one_or_none()
    if context is None:
        return {"content": "", "updated_at": None}
    return {"content": context.content, "updated_at": context.updated_at.isoformat()}


async def update_my_agent_context(
    *,
    claims: dict[str, object],
    content: str,
    session: AsyncSession,
) -> dict[str, object]:
    if len(content) > AGENT_CONTEXT_MAX_LENGTH:
        raise HttpError(422, f"content must be at most {AGENT_CONTEXT_MAX_LENGTH} characters")
    try:
        tenant = await tenant_from_claims(claims=claims, session=session)
    except ValueError as error:
        raise HttpError(401, str(error)) from error

    result = await session.execute(
        select(TenantAgentContext).where(TenantAgentContext.tenant_id == tenant.id),
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        existing.content = content
        existing.updated_at = now
        await session.commit()
        await session.refresh(existing)
        return {"content": existing.content, "updated_at": existing.updated_at.isoformat()}

    row = TenantAgentContext(tenant_id=tenant.id, content=content, updated_at=now)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {"content": row.content, "updated_at": row.updated_at.isoformat()}
