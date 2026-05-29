"""Tenant lookup and creation for Auth0 users."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.github.models import Tenant

logger = structlog.getLogger(__name__)


def _default_tenant_name(*, email: str | None, name: str | None, auth0_sub: str) -> str:
    if name and name.strip():
        return name.strip()
    if email:
        local_part = email.split("@", 1)[0]
        return local_part or email
    return auth0_sub


async def get_or_create_tenant_for_auth_user(
    *,
    auth0_sub: str,
    email: str | None,
    name: str | None,
    session: AsyncSession,
) -> Tenant:
    """Return the tenant for an Auth0 user, creating one on first login/signup."""
    result = await session.execute(select(Tenant).where(Tenant.auth0_sub == auth0_sub))
    tenant = result.scalar_one_or_none()
    if tenant is not None:
        if email and tenant.email != email.strip().lower():
            tenant.email = email.strip().lower()
            await session.commit()
            await session.refresh(tenant)
        logger.info("tenant_login_resolved", tenant_id=tenant.id, auth0_sub=auth0_sub)
        return tenant

    normalized_email = email.strip().lower() if email else None
    tenant = Tenant(
        auth0_sub=auth0_sub,
        name=_default_tenant_name(email=normalized_email, name=name, auth0_sub=auth0_sub),
        email=normalized_email,
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    logger.info("tenant_registered", tenant_id=tenant.id, auth0_sub=auth0_sub, email=normalized_email)
    return tenant
