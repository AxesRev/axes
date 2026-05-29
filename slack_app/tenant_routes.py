"""Tenant API secured with Auth0 access tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from slack_app.auth0 import require_auth0_claims
from slack_app.tenant_schemas import TenantResponse
from slack_app.tenant_service import get_or_create_tenant_for_auth_user

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _claim_str(claims: dict[str, object], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


@router.get("/me", response_model=TenantResponse)
async def get_my_tenant(
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> TenantResponse:
    """Resolve the caller's tenant from a validated Auth0 access token."""
    auth0_sub = _claim_str(claims, "sub")
    if not auth0_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing sub claim",
        )

    tenant = await get_or_create_tenant_for_auth_user(
        auth0_sub=auth0_sub,
        email=_claim_str(claims, "email"),
        name=_claim_str(claims, "name"),
        session=session,
    )
    return TenantResponse(id=tenant.id, name=tenant.name, email=tenant.email)
