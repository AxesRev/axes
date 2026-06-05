"""Tenant billing: Paddle reference IDs and monthly token usage charges."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import structlog
from aegra_api.core.orm import Run
from app_integrations.github.models import Tenant, UserIdentity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.config import billing_settings
from billing.paddle_client import PaddleApiError, charge_subscription_usage, create_customer_portal_url
from billing.schemas import BillingChargeUsageResponse, BillingPortalResponse, TenantBillingStatusResponse

logger = structlog.getLogger(__name__)


def sum_tokens_from_usage(token_usage: dict[str, Any] | None) -> int:
    if not token_usage:
        return 0

    total = 0
    for metadata in token_usage.values():
        if not isinstance(metadata, dict):
            continue
        raw_total = metadata.get("total_tokens")
        if isinstance(raw_total, int):
            total += raw_total
        elif isinstance(raw_total, str) and raw_total.isdigit():
            total += int(raw_total)
    return total


async def _tenant_user_ids(*, tenant: Tenant, session: AsyncSession) -> list[str]:
    user_ids: list[str] = []
    if tenant.auth0_sub:
        user_ids.append(tenant.auth0_sub)

    result = await session.execute(
        select(UserIdentity.slack_user_id).where(UserIdentity.tenant_id == tenant.id),
    )
    user_ids.extend(result.scalars().all())
    return user_ids


async def aggregate_tenant_token_usage(
    *,
    tenant: Tenant,
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
) -> int:
    user_ids = await _tenant_user_ids(tenant=tenant, session=session)
    if not user_ids:
        return 0

    result = await session.execute(
        select(Run.token_usage).where(
            Run.user_id.in_(user_ids),
            Run.status == "success",
            Run.created_at >= period_start,
            Run.created_at < period_end,
            Run.token_usage.isnot(None),
        ),
    )
    total_tokens = 0
    for token_usage in result.scalars().all():
        if isinstance(token_usage, dict):
            total_tokens += sum_tokens_from_usage(token_usage)
    return total_tokens


def _billing_setup(tenant: Tenant) -> bool:
    return bool(tenant.paddle_customer_id and tenant.paddle_subscription_id)


def get_tenant_billing_status(*, tenant: Tenant) -> TenantBillingStatusResponse:
    return TenantBillingStatusResponse(
        billing_setup=_billing_setup(tenant),
        paddle_customer_id=tenant.paddle_customer_id,
        paddle_subscription_id=tenant.paddle_subscription_id,
        subscription_status=tenant.paddle_subscription_status,
    )


async def create_tenant_billing_portal_url(*, tenant: Tenant) -> BillingPortalResponse:
    if not tenant.paddle_customer_id or not tenant.paddle_subscription_id:
        raise ValueError("Billing is not set up for this tenant")

    url = await create_customer_portal_url(
        customer_id=tenant.paddle_customer_id,
        subscription_id=tenant.paddle_subscription_id,
    )
    return BillingPortalResponse(url=url)


def _tenant_id_from_custom_data(custom_data: object) -> str | None:
    if not isinstance(custom_data, dict):
        return None
    tenant_id = custom_data.get("tenant_id")
    return tenant_id if isinstance(tenant_id, str) and tenant_id else None


async def _apply_tenant_billing_link(
    *,
    tenant: Tenant,
    paddle_customer_id: str,
    paddle_subscription_id: str,
    paddle_subscription_status: str | None,
    session: AsyncSession,
) -> None:
    tenant.paddle_customer_id = paddle_customer_id
    tenant.paddle_subscription_id = paddle_subscription_id
    tenant.paddle_subscription_status = paddle_subscription_status
    await session.commit()
    await session.refresh(tenant)

    logger.info(
        "tenant_paddle_billing_linked",
        tenant_id=tenant.id,
        paddle_customer_id=paddle_customer_id,
        paddle_subscription_id=paddle_subscription_id,
        paddle_subscription_status=paddle_subscription_status,
    )


async def handle_subscription_created_webhook(
    *,
    subscription: dict[str, Any],
    session: AsyncSession,
) -> None:
    tenant_id = _tenant_id_from_custom_data(subscription.get("custom_data"))
    if tenant_id is None:
        logger.warning("billing_webhook_subscription_created_missing_tenant_id")
        return

    customer_id = subscription.get("customer_id")
    subscription_id = subscription.get("id")
    status = subscription.get("status")
    if not isinstance(customer_id, str) or not isinstance(subscription_id, str):
        logger.warning(
            "billing_webhook_subscription_created_missing_ids",
            tenant_id=tenant_id,
        )
        return

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        logger.warning("billing_webhook_subscription_created_tenant_not_found", tenant_id=tenant_id)
        return

    subscription_status = status if isinstance(status, str) else None
    await _apply_tenant_billing_link(
        tenant=tenant,
        paddle_customer_id=customer_id,
        paddle_subscription_id=subscription_id,
        paddle_subscription_status=subscription_status,
        session=session,
    )


async def handle_subscription_updated_webhook(
    *,
    subscription: dict[str, Any],
    session: AsyncSession,
) -> None:
    subscription_id = subscription.get("id")
    if not isinstance(subscription_id, str) or not subscription_id:
        return

    result = await session.execute(
        select(Tenant).where(Tenant.paddle_subscription_id == subscription_id),
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return

    status = subscription.get("status")
    tenant.paddle_subscription_status = status if isinstance(status, str) else None
    await session.commit()

    logger.info(
        "tenant_paddle_subscription_status_updated",
        tenant_id=tenant.id,
        paddle_subscription_id=subscription_id,
        paddle_subscription_status=tenant.paddle_subscription_status,
    )


async def handle_transaction_completed_webhook(
    *,
    transaction: dict[str, Any],
    session: AsyncSession,
) -> None:
    tenant_id = _tenant_id_from_custom_data(transaction.get("custom_data"))
    if tenant_id is None:
        return

    customer_id = transaction.get("customer_id")
    subscription_id = transaction.get("subscription_id")
    if not isinstance(customer_id, str) or not isinstance(subscription_id, str):
        return

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        logger.warning("billing_webhook_transaction_completed_tenant_not_found", tenant_id=tenant_id)
        return

    if tenant.paddle_subscription_id == subscription_id and tenant.paddle_customer_id == customer_id:
        return

    await _apply_tenant_billing_link(
        tenant=tenant,
        paddle_customer_id=customer_id,
        paddle_subscription_id=subscription_id,
        paddle_subscription_status=tenant.paddle_subscription_status,
        session=session,
    )


async def handle_paddle_webhook_event(
    *,
    event_type: str,
    data: dict[str, Any],
    session: AsyncSession,
) -> None:
    if event_type == "subscription.created":
        await handle_subscription_created_webhook(subscription=data, session=session)
        return

    if event_type == "subscription.updated":
        await handle_subscription_updated_webhook(subscription=data, session=session)
        return

    if event_type == "transaction.completed":
        await handle_transaction_completed_webhook(transaction=data, session=session)


def _usage_quantity(total_tokens: int) -> int:
    if total_tokens <= 0:
        return 0
    tokens_per_unit = billing_settings.BILLING_TOKENS_PER_UNIT
    return max(1, math.ceil(total_tokens / tokens_per_unit))


async def charge_monthly_usage_for_all_tenants(
    *,
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
) -> BillingChargeUsageResponse:
    usage_price_id = billing_settings.PADDLE_USAGE_PRICE_ID.strip()
    if not usage_price_id:
        raise ValueError("PADDLE_USAGE_PRICE_ID is not configured")

    result = await session.execute(
        select(Tenant).where(
            Tenant.paddle_subscription_id.isnot(None),
            Tenant.paddle_customer_id.isnot(None),
        ),
    )
    tenants = result.scalars().all()

    charged = 0
    skipped = 0
    details: list[dict[str, object]] = []

    for tenant in tenants:
        assert tenant.paddle_subscription_id is not None
        total_tokens = await aggregate_tenant_token_usage(
            tenant=tenant,
            session=session,
            period_start=period_start,
            period_end=period_end,
        )
        quantity = _usage_quantity(total_tokens)

        if quantity == 0:
            skipped += 1
            details.append({"tenant_id": tenant.id, "status": "skipped", "total_tokens": 0})
            continue

        try:
            await charge_subscription_usage(
                subscription_id=tenant.paddle_subscription_id,
                price_id=usage_price_id,
                quantity=quantity,
            )
            charged += 1
            details.append(
                {
                    "tenant_id": tenant.id,
                    "status": "charged",
                    "total_tokens": total_tokens,
                    "quantity": quantity,
                },
            )
        except PaddleApiError as error:
            skipped += 1
            details.append(
                {
                    "tenant_id": tenant.id,
                    "status": "error",
                    "total_tokens": total_tokens,
                    "quantity": quantity,
                    "detail": error.detail,
                },
            )
            logger.error(
                "tenant_usage_charge_failed",
                tenant_id=tenant.id,
                subscription_id=tenant.paddle_subscription_id,
                detail=error.detail,
            )

    return BillingChargeUsageResponse(
        tenants_charged=charged,
        tenants_skipped=skipped,
        details=details,
    )


def current_month_period() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        period_end = period_start.replace(year=now.year + 1, month=1)
    else:
        period_end = period_start.replace(month=now.month + 1)
    return period_start, period_end
