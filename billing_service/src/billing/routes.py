"""Billing HTTP API. Public paths are /billing/*, not /tenants/*."""

from __future__ import annotations

import json

import httpx
import structlog
from aegra_api.core.orm import get_session
from fastapi import APIRouter, Depends, HTTPException, Request, status
from slack_app.auth0 import require_auth0_claims
from sqlalchemy.ext.asyncio import AsyncSession

from billing.config import billing_settings
from billing.paddle_client import PaddleApiError
from billing.schemas import BillingPortalResponse, TenantBillingStatusResponse
from billing.service import create_tenant_billing_portal_url, get_tenant_billing_status, handle_paddle_webhook_event
from billing.tenant_client import resolve_tenant_for_auth_user
from billing.webhooks import WebhookVerificationError, verify_paddle_webhook_signature
from tenant.models import Tenant

router = APIRouter(prefix="/billing", tags=["billing"])

logger = structlog.getLogger(__name__)


def _claim_str(claims: dict[str, object], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


async def _tenant_for_billing_user(
    claims: dict,
    session: AsyncSession,
) -> Tenant:
    auth0_sub = _claim_str(claims, "sub")
    if not auth0_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing sub claim",
        )
    try:
        ref = await resolve_tenant_for_auth_user(
            auth0_sub=auth0_sub,
            email=_claim_str(claims, "email"),
            name=_claim_str(claims, "name"),
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    except httpx.HTTPError as error:
        logger.error("billing_tenant_resolve_failed", error=str(error))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not resolve tenant",
        ) from error

    tenant = await session.get(Tenant, ref.id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return tenant


@router.get("/me", response_model=TenantBillingStatusResponse)
async def get_my_billing(
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> TenantBillingStatusResponse:
    tenant = await _tenant_for_billing_user(claims, session)
    return get_tenant_billing_status(tenant=tenant)


@router.post("/me/portal", response_model=BillingPortalResponse)
async def create_my_billing_portal(
    claims: dict = Depends(require_auth0_claims),
    session: AsyncSession = Depends(get_session),
) -> BillingPortalResponse:
    if not billing_settings.PADDLE_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paddle billing is not configured on the server",
        )

    tenant = await _tenant_for_billing_user(claims, session)

    try:
        return await create_tenant_billing_portal_url(tenant=tenant)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except PaddleApiError as error:
        logger.error(
            "billing_portal_paddle_error",
            detail=error.detail,
            status_code=error.status_code,
            tenant_id=tenant.id,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error.detail) from error


@router.post("/webhooks")
async def paddle_billing_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    raw_body = await request.body()
    signature_header = request.headers.get("Paddle-Signature")

    try:
        verify_paddle_webhook_signature(
            raw_body=raw_body,
            signature_header=signature_header,
            secret_key=billing_settings.PADDLE_WEBHOOK_SECRET,
        )
    except WebhookVerificationError as error:
        logger.warning("billing_webhook_verification_failed", detail=str(error))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    try:
        payload = json.loads(raw_body)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from error

    event_type = payload.get("event_type")
    data = payload.get("data")
    if not isinstance(event_type, str) or not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")

    await handle_paddle_webhook_event(event_type=event_type, data=data, session=session)
    return {"ok": True}
