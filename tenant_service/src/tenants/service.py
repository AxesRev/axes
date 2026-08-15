"""Tenant lookup and creation for Auth0 users."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.models import Tenant


def _default_tenant_name(*, email: str | None, name: str | None, auth0_sub: str) -> str:
    if name and name.strip():
        return name.strip()
    if email:
        local_part = email.split("@", 1)[0]
        return local_part or email
    return auth0_sub


def _claim_str(claims: dict[str, object], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


async def get_or_create_tenant_for_auth_user(
    *,
    auth0_sub: str,
    email: str | None,
    name: str | None,
    session: AsyncSession,
) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.auth0_sub == auth0_sub))
    tenant = result.scalar_one_or_none()
    if tenant is not None:
        if email and tenant.email != email.strip().lower():
            tenant.email = email.strip().lower()
            await session.commit()
            await session.refresh(tenant)
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
    return tenant


async def tenant_from_claims(*, claims: dict[str, object], session: AsyncSession) -> Tenant:
    auth0_sub = _claim_str(claims, "sub")
    if not auth0_sub:
        raise ValueError("Access token is missing sub claim")
    return await get_or_create_tenant_for_auth_user(
        auth0_sub=auth0_sub,
        email=_claim_str(claims, "email"),
        name=_claim_str(claims, "name"),
        session=session,
    )
