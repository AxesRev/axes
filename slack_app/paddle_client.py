"""Minimal Paddle Billing API client (sandbox). Card data never passes through here."""

from __future__ import annotations

import json
from typing import Any

import httpx

from slack_app.config import billing_settings

PADDLE_SANDBOX_API_BASE = "https://sandbox-api.paddle.com"


class PaddleApiError(Exception):
    """Raised when the Paddle API returns an error response."""

    def __init__(self, *, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Paddle API error ({status_code}): {detail}")


def _format_api_error(*, status_code: int, body: str) -> str:
    try:
        payload = json.loads(body)
    except ValueError:
        return body or f"HTTP {status_code}"

    error = payload.get("error")
    if not isinstance(error, dict):
        return body or f"HTTP {status_code}"

    code = error.get("code")
    detail = error.get("detail")
    if code == "invalid_token":
        return (
            "Invalid Paddle API key. Use a sandbox key (pdl_sdbx_apikey_...) in root .env, "
            "ensure it has transaction.read permission, and restart the API server."
        )
    if isinstance(detail, str) and detail:
        if code == "forbidden":
            return f"{detail} Ensure the API key has transaction.read and subscription.read permissions."
        return detail
    return body or f"HTTP {status_code}"


def _api_key() -> str:
    api_key = billing_settings.PADDLE_API_KEY.strip()
    if not api_key:
        raise PaddleApiError(status_code=503, detail="Paddle API key is not configured")
    return api_key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


async def paddle_get(path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{PADDLE_SANDBOX_API_BASE}{path}", headers=_headers())
    if response.status_code >= 400:
        raise PaddleApiError(
            status_code=response.status_code,
            detail=_format_api_error(status_code=response.status_code, body=response.text),
        )
    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PaddleApiError(status_code=502, detail="Paddle response missing data object")
    return data


async def paddle_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{PADDLE_SANDBOX_API_BASE}{path}", headers=_headers(), json=body)
    if response.status_code >= 400:
        raise PaddleApiError(
            status_code=response.status_code,
            detail=_format_api_error(status_code=response.status_code, body=response.text),
        )
    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PaddleApiError(status_code=502, detail="Paddle response missing data object")
    return data


async def get_transaction(transaction_id: str) -> dict[str, Any]:
    return await paddle_get(f"/transactions/{transaction_id}")


async def get_subscription(subscription_id: str) -> dict[str, Any]:
    return await paddle_get(f"/subscriptions/{subscription_id}")


async def list_subscriptions_for_customer(customer_id: str) -> list[dict[str, Any]]:
    """Return all subscriptions for a customer, most recently created first."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{PADDLE_SANDBOX_API_BASE}/subscriptions",
            headers=_headers(),
            params={"customer_id": customer_id, "per_page": "10"},
        )
    if response.status_code >= 400:
        raise PaddleApiError(
            status_code=response.status_code,
            detail=_format_api_error(status_code=response.status_code, body=response.text),
        )
    payload = response.json()
    data = payload.get("data")
    return data if isinstance(data, list) else []


async def charge_subscription_usage(
    *,
    subscription_id: str,
    price_id: str,
    quantity: int,
) -> dict[str, Any]:
    return await paddle_post(
        f"/subscriptions/{subscription_id}/charge",
        {
            "effective_from": "next_billing_period",
            "items": [{"price_id": price_id, "quantity": quantity}],
        },
    )
