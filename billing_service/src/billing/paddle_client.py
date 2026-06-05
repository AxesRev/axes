"""Minimal Paddle Billing API client (sandbox). Card data never passes through here."""

from __future__ import annotations

import json
from typing import Any

import httpx

from billing.config import billing_settings

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
            "ensure it has the required permissions, and restart the API server."
        )
    if isinstance(detail, str) and detail:
        if code == "forbidden":
            return f"{detail} Ensure the API key has the required Paddle permissions."
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


async def create_customer_portal_url(*, customer_id: str, subscription_id: str) -> str:
    session = await paddle_post(
        f"/customers/{customer_id}/portal-sessions",
        {"subscription_ids": [subscription_id]},
    )
    urls = session.get("urls")
    if not isinstance(urls, dict):
        raise PaddleApiError(status_code=502, detail="Paddle portal session missing urls")

    subscriptions = urls.get("subscriptions")
    if isinstance(subscriptions, list) and subscriptions:
        first = subscriptions[0]
        if isinstance(first, dict):
            update_url = first.get("update_subscription_payment_method")
            if isinstance(update_url, str) and update_url:
                return update_url

    general = urls.get("general")
    if isinstance(general, dict):
        overview = general.get("overview")
        if isinstance(overview, str) and overview:
            return overview

    raise PaddleApiError(status_code=502, detail="Paddle did not return a customer portal URL")


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
