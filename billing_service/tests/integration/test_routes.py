"""Integration tests for billing Lambda HTTP handler."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

from billing.app import handler

INTERNAL_SECRET = "test-internal-secret"


def _webhook_signature(*, body: bytes, secret: str) -> str:
    timestamp = int(time.time())
    signed_payload = f"{timestamp}:".encode() + body
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"ts={timestamp};h1={signature}"


def _event(
    *,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: str | bytes | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": headers or {},
        "isBase64Encoded": False,
    }
    if body is not None:
        payload["body"] = body.decode() if isinstance(body, bytes) else body
    return payload


def _invoke(**kwargs: Any) -> tuple[int, dict[str, object]]:
    response = handler(_event(**kwargs), None)
    return int(response["statusCode"]), json.loads(str(response["body"]))


@pytest.fixture
def billing_session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    session = AsyncMock()

    @asynccontextmanager
    async def fake_session() -> Any:
        yield session

    async def fake_with_session() -> Any:
        return fake_session()

    monkeypatch.setattr("billing.app._with_session", fake_with_session)
    monkeypatch.setattr("billing.config.billing_settings.INTERNAL_API_SECRET", INTERNAL_SECRET)
    monkeypatch.setattr("billing.app.billing_settings.INTERNAL_API_SECRET", INTERNAL_SECRET)
    monkeypatch.setattr("billing.config.billing_settings.PADDLE_API_KEY", "test_sdbx_key")
    return session


@pytest.mark.integration
def test_get_my_tenant_billing_requires_internal_secret() -> None:
    status_code, payload = _invoke(method="GET", path="/billing/me")
    assert status_code == 401
    assert payload["detail"] == "Invalid internal secret"


@pytest.mark.integration
def test_health() -> None:
    status_code, payload = _invoke(method="GET", path="/health")
    assert status_code == 200
    assert payload == {"status": "healthy", "service": "billing"}


@pytest.mark.integration
def test_get_my_tenant_billing_returns_not_setup(billing_session: AsyncMock) -> None:
    billing_session.get = AsyncMock(return_value=None)

    status_code, payload = _invoke(
        method="GET",
        path="/billing/me",
        headers={"X-Internal-Secret": INTERNAL_SECRET, "X-Tenant-Id": "tenant-new"},
    )
    assert status_code == 200
    assert payload == {
        "billing_setup": False,
        "paddle_customer_id": None,
        "paddle_subscription_id": None,
        "subscription_status": None,
    }


@pytest.mark.integration
def test_create_my_tenant_billing_portal_returns_url(
    billing_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from billing.models import BillingAccount
    from billing.schemas import BillingPortalResponse

    account = BillingAccount(
        tenant_id="tenant-new",
        paddle_customer_id="ctm_123",
        paddle_subscription_id="sub_123",
    )
    billing_session.get = AsyncMock(return_value=account)

    async def fake_portal(**kwargs: object) -> BillingPortalResponse:
        return BillingPortalResponse(url="https://sandbox-customer-portal.paddle.com/example")

    monkeypatch.setattr("billing.routes.create_tenant_billing_portal_url", fake_portal)

    status_code, payload = _invoke(
        method="POST",
        path="/billing/me/portal",
        headers={"X-Internal-Secret": INTERNAL_SECRET, "X-Tenant-Id": "tenant-new"},
    )
    assert status_code == 200
    assert payload == {"url": "https://sandbox-customer-portal.paddle.com/example"}


@pytest.mark.integration
def test_paddle_billing_webhook_accepts_valid_event(
    billing_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "whsec_integration_test"
    monkeypatch.setattr("billing.config.billing_settings.PADDLE_WEBHOOK_SECRET", secret)

    handled = AsyncMock()

    async def fake_handle(**kwargs: object) -> None:
        await handled()

    monkeypatch.setattr("billing.routes.handle_paddle_webhook_event", fake_handle)

    body = json.dumps(
        {
            "event_type": "subscription.created",
            "data": {
                "id": "sub_123",
                "customer_id": "ctm_123",
                "status": "active",
                "custom_data": {"tenant_id": "tenant-1"},
            },
        },
    ).encode()
    status_code, payload = _invoke(
        method="POST",
        path="/billing/webhooks",
        headers={"Paddle-Signature": _webhook_signature(body=body, secret=secret)},
        body=body,
    )

    assert status_code == 200
    assert payload == {"ok": True}
    handled.assert_awaited_once()


@pytest.mark.integration
def test_paddle_billing_webhook_rejects_invalid_signature(
    billing_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("billing.config.billing_settings.PADDLE_WEBHOOK_SECRET", "whsec_integration_test")

    status_code, payload = _invoke(
        method="POST",
        path="/billing/webhooks",
        headers={"Paddle-Signature": "ts=1;h1=invalid"},
        body=json.dumps({"event_type": "subscription.created", "data": {}}),
    )

    assert status_code == 401
    assert "detail" in payload
