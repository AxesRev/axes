"""Unit tests for Paddle webhook event handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app_integrations.github.models import Tenant

from billing.service import (
    get_tenant_billing_status,
    handle_subscription_created_webhook,
    handle_subscription_updated_webhook,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_subscription_created_webhook_links_tenant() -> None:
    tenant = Tenant(
        id="tenant-1",
        name="Owner",
        email="owner@example.com",
        auth0_sub="auth0|123",
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=tenant)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    await handle_subscription_created_webhook(
        subscription={
            "id": "sub_123",
            "customer_id": "ctm_123",
            "status": "active",
            "custom_data": {"tenant_id": "tenant-1"},
        },
        session=session,
    )

    assert tenant.paddle_customer_id == "ctm_123"
    assert tenant.paddle_subscription_id == "sub_123"
    assert tenant.paddle_subscription_status == "active"
    session.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_subscription_updated_webhook_updates_status() -> None:
    tenant = Tenant(
        id="tenant-1",
        name="Owner",
        email="owner@example.com",
        auth0_sub="auth0|123",
        paddle_customer_id="ctm_123",
        paddle_subscription_id="sub_123",
        paddle_subscription_status="active",
    )
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = tenant
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()

    await handle_subscription_updated_webhook(
        subscription={"id": "sub_123", "status": "past_due"},
        session=session,
    )

    assert tenant.paddle_subscription_status == "past_due"
    session.commit.assert_awaited_once()


@pytest.mark.unit
def test_get_tenant_billing_status_reads_db_only() -> None:
    tenant = Tenant(
        id="tenant-1",
        name="Owner",
        email="owner@example.com",
        auth0_sub="auth0|123",
        paddle_customer_id="ctm_123",
        paddle_subscription_id="sub_123",
        paddle_subscription_status="active",
    )

    status = get_tenant_billing_status(tenant=tenant)

    assert status.billing_setup is True
    assert status.paddle_customer_id == "ctm_123"
    assert status.paddle_subscription_id == "sub_123"
    assert status.subscription_status == "active"
