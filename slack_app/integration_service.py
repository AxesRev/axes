"""Tenant app integration queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.github.models import AppIntegration


async def list_app_integrations_for_tenant(
    *,
    tenant_id: str,
    session: AsyncSession,
) -> list[AppIntegration]:
    """Return all app integrations linked to a tenant."""
    result = await session.execute(
        select(AppIntegration).where(AppIntegration.tenant_id == tenant_id).order_by(AppIntegration.app_name)
    )
    return list(result.scalars().all())
