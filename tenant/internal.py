"""Internal tenant API for other services (billing, slack). Not Auth0 user routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from tenant.config import tenant_settings
from tenant.schemas import TenantResponse
from tenant.service import get_or_create_tenant_for_auth_user

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    expected = tenant_settings.INTERNAL_API_SECRET
    if not expected or x_internal_secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal secret")


class ResolveTenantBody(BaseModel):
    auth0_sub: str
    email: str | None = None
    name: str | None = None


@router.post("/tenants/resolve", response_model=TenantResponse)
async def resolve_tenant(
    body: ResolveTenantBody,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(_require_internal_secret),
) -> TenantResponse:
    tenant = await get_or_create_tenant_for_auth_user(
        auth0_sub=body.auth0_sub,
        email=body.email,
        name=body.name,
        session=session,
    )
    return TenantResponse(id=tenant.id, name=tenant.name, email=tenant.email)
