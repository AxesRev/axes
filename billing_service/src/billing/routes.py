"""Billing HTTP use-cases. Called from the Lambda handler, not FastAPI."""

from __future__ import annotations

import json

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from billing.config import billing_settings
from billing.errors import HttpError
from billing.paddle_client import PaddleApiError
from billing.service import create_tenant_billing_portal_url, get_tenant_billing_status, handle_paddle_webhook_event
from billing.tenant_client import resolve_tenant_for_auth_user
from billing.webhooks import WebhookVerificationError, verify_paddle_webhook_signature
from tenant.models import Tenant

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
        raise HttpError(401, "Access token is missing sub claim")
    try:
        ref = await resolve_tenant_for_auth_user(
            auth0_sub=auth0_sub,
            email=_claim_str(claims, "email"),
            name=_claim_str(claims, "name"),
        )
    except PermissionError as error:
        raise HttpError(401, str(error)) from error
    except httpx.HTTPError as error:
        logger.error("billing_tenant_resolve_failed", error=str(error))
        raise HttpError(502, "Could not resolve tenant") from error

    tenant = await session.get(Tenant, ref.id)
    if tenant is None:
        raise HttpError(404, "tenant not found")
    return tenant


async def get_my_billing(*, claims: dict, session: AsyncSession) -> dict[str, object]:
    tenant = await _tenant_for_billing_user(claims, session)
    return get_tenant_billing_status(tenant=tenant).model_dump()


async def create_my_billing_portal(*, claims: dict, session: AsyncSession) -> dict[str, object]:
    if not billing_settings.PADDLE_API_KEY.strip():
        raise HttpError(503, "Paddle billing is not configured on the server")

    tenant = await _tenant_for_billing_user(claims, session)

    try:
        portal = await create_tenant_billing_portal_url(tenant=tenant)
    except ValueError as error:
        raise HttpError(404, str(error)) from error
    except PaddleApiError as error:
        logger.error(
            "billing_portal_paddle_error",
            detail=error.detail,
            status_code=error.status_code,
            tenant_id=tenant.id,
        )
        raise HttpError(502, error.detail) from error
    return portal.model_dump()


async def paddle_billing_webhook(
    *, raw_body: bytes, signature_header: str | None, session: AsyncSession
) -> dict[str, bool]:
    try:
        verify_paddle_webhook_signature(
            raw_body=raw_body,
            signature_header=signature_header,
            secret_key=billing_settings.PADDLE_WEBHOOK_SECRET,
        )
    except WebhookVerificationError as error:
        logger.warning("billing_webhook_verification_failed", detail=str(error))
        raise HttpError(401, str(error)) from error

    try:
        payload = json.loads(raw_body)
    except ValueError as error:
        raise HttpError(400, "Invalid JSON body") from error

    event_type = payload.get("event_type")
    data = payload.get("data")
    if not isinstance(event_type, str) or not isinstance(data, dict):
        raise HttpError(400, "Invalid webhook payload")

    await handle_paddle_webhook_event(event_type=event_type, data=data, session=session)
    return {"ok": True}
