"""Tenant billing routes secured with Auth0 access tokens."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from slack_app.auth0 import require_auth0_claims
from slack_app.billing_schemas import BillingLinkRequest, BillingLinkResponse, TenantBillingStatusResponse
from slack_app.billing_service import get_tenant_billing_status, link_tenant_paddle_billing
from slack_app.config import billing_settings
from slack_app.paddle_client import PaddleApiError
from slack_app.tenant_service import get_or_create_tenant_for_auth_user

router = APIRouter(tags=["billing"])

logger = structlog.getLogger(__name__)


def _claim_str(claims: dict[str, object], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


@router.get("/tenants/me/billing", response_model=TenantBillingStatusResponse)
async def get_my_tenant_billing(
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> TenantBillingStatusResponse:
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
    return await get_tenant_billing_status(tenant=tenant)


@router.post("/tenants/me/billing/link", response_model=BillingLinkResponse)
async def link_my_tenant_billing(
    request: BillingLinkRequest,
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> BillingLinkResponse:
    if not billing_settings.PADDLE_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paddle billing is not configured on the server",
        )

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
        return await link_tenant_paddle_billing(
            tenant=tenant,
            paddle_customer_id=request.paddle_customer_id,
            paddle_transaction_id=request.paddle_transaction_id,
            session=session,
        )
    except ValueError as error:
        logger.warning(
            "billing_link_validation_failed",
            detail=str(error),
            tenant_id=tenant.id,
            paddle_customer_id=request.paddle_customer_id,
            paddle_transaction_id=request.paddle_transaction_id,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except PaddleApiError as error:
        logger.error(
            "billing_link_paddle_error",
            detail=error.detail,
            status_code=error.status_code,
            tenant_id=tenant.id,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error.detail) from error
