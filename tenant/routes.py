"""Tenant API secured with Auth0 access tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from slack_app.auth0 import require_auth0_claims
from tenant.agent_context_service import get_agent_context_for_tenant, upsert_agent_context_for_tenant
from tenant.integration_service import list_app_integrations_for_tenant
from tenant.schemas import AgentContextResponse, AgentContextUpdateRequest, AppIntegrationResponse, TenantResponse
from tenant.service import get_or_create_tenant_for_auth_user

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


@router.get("/me/integrations", response_model=list[AppIntegrationResponse])
async def get_my_app_integrations(
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> list[AppIntegrationResponse]:
    """List app integrations for the caller's tenant."""
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
    integrations = await list_app_integrations_for_tenant(tenant_id=tenant.id, session=session)
    return [
        AppIntegrationResponse(id=integration.id, app_name=integration.app_name, config=integration.config)
        for integration in integrations
    ]


@router.get("/me/agent-context", response_model=AgentContextResponse)
async def get_my_agent_context(
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> AgentContextResponse:
    """Return the caller's tenant agent context text."""
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
    context = await get_agent_context_for_tenant(tenant_id=tenant.id, session=session)
    if context is None:
        return AgentContextResponse(content="", updated_at=None)
    return AgentContextResponse(content=context.content, updated_at=context.updated_at)


@router.put("/me/agent-context", response_model=AgentContextResponse)
async def update_my_agent_context(
    body: AgentContextUpdateRequest,
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> AgentContextResponse:
    """Create or update the caller's tenant agent context text."""
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
    try:
        context = await upsert_agent_context_for_tenant(
            tenant_id=tenant.id,
            content=body.content,
            session=session,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    return AgentContextResponse(content=context.content, updated_at=context.updated_at)
