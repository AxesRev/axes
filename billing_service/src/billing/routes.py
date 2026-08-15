"""Billing HTTP use-cases. Called from the Lambda handler, not FastAPI."""

from __future__ import annotations

import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from billing.config import billing_settings
from billing.errors import HttpError
from billing.models import Tenant
from billing.paddle_client import PaddleApiError
from billing.service import create_tenant_billing_portal_url, get_tenant_billing_status, handle_paddle_webhook_event
from billing.webhooks import WebhookVerificationError, verify_paddle_webhook_signature

logger = structlog.getLogger(__name__)


async def _tenant_by_id(*, tenant_id: str, session: AsyncSession) -> Tenant:
    if not tenant_id.strip():
        raise HttpError(400, "tenant_id is required")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HttpError(404, "tenant not found")
    return tenant


async def get_my_billing(*, tenant_id: str, session: AsyncSession) -> dict[str, object]:
    tenant = await _tenant_by_id(tenant_id=tenant_id, session=session)
    return get_tenant_billing_status(tenant=tenant).model_dump()


async def create_my_billing_portal(*, tenant_id: str, session: AsyncSession) -> dict[str, object]:
    if not billing_settings.PADDLE_API_KEY.strip():
        raise HttpError(503, "Paddle billing is not configured on the server")

    tenant = await _tenant_by_id(tenant_id=tenant_id, session=session)

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
