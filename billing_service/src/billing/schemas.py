"""Pydantic schemas for tenant billing routes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TenantBillingStatusResponse(BaseModel):
    billing_setup: bool
    paddle_customer_id: str | None
    paddle_subscription_id: str | None
    subscription_status: str | None = None


class BillingPortalResponse(BaseModel):
    url: str = Field(min_length=1)


class BillingChargeUsageResponse(BaseModel):
    tenants_charged: int
    tenants_skipped: int
    details: list[dict[str, object]] = Field(default_factory=list)
