"""API Gateway HTTP API (payload 2.0) Lambda handler for billing."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
from typing import Any

from billing.config import billing_settings
from billing.db import session_scope
from billing.errors import HttpError
from billing.routes import create_my_billing_portal, get_my_billing, paddle_billing_webhook


def _json_response(status_code: int, payload: dict[str, object]) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _header(event: dict[str, Any], name: str) -> str | None:
    headers = event.get("headers") or {}
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target and isinstance(value, str):
            return value
    return None


def _query(event: dict[str, Any], name: str) -> str | None:
    params = event.get("queryStringParameters") or {}
    value = params.get(name)
    return value if isinstance(value, str) and value else None


def _method_and_path(event: dict[str, Any]) -> tuple[str, str]:
    context = event.get("requestContext") or {}
    http = context.get("http") or {}
    method = str(http.get("method") or event.get("httpMethod") or "GET").upper()
    path = str(event.get("rawPath") or event.get("path") or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return method, path


def _body_bytes(event: dict[str, Any]) -> bytes:
    body = event.get("body")
    if body is None:
        return b""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    if isinstance(body, bytes):
        return body
    return str(body).encode()


def _require_internal_secret(event: dict[str, Any]) -> None:
    expected = billing_settings.INTERNAL_API_SECRET
    provided = _header(event, "x-internal-secret")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HttpError(401, "Invalid internal secret")


def _tenant_id(event: dict[str, Any]) -> str:
    tenant_id = _header(event, "x-tenant-id") or _query(event, "tenant_id")
    if not tenant_id:
        raise HttpError(400, "tenant_id is required")
    return tenant_id


async def _with_session():
    return session_scope()


async def _handle(event: dict[str, Any]) -> dict[str, object]:
    method, path = _method_and_path(event)
    if method == "GET" and path == "/health":
        return _json_response(200, {"status": "healthy", "service": "billing"})

    try:
        if method == "GET" and path == "/billing/me":
            _require_internal_secret(event)
            async with await _with_session() as session:
                payload = await get_my_billing(tenant_id=_tenant_id(event), session=session)
            return _json_response(200, payload)

        if method == "POST" and path == "/billing/me/portal":
            _require_internal_secret(event)
            async with await _with_session() as session:
                payload = await create_my_billing_portal(tenant_id=_tenant_id(event), session=session)
            return _json_response(200, payload)

        if method == "POST" and path == "/billing/webhooks":
            async with await _with_session() as session:
                payload = await paddle_billing_webhook(
                    raw_body=_body_bytes(event),
                    signature_header=_header(event, "paddle-signature"),
                    session=session,
                )
            return _json_response(200, payload)
    except HttpError as error:
        return _json_response(error.status_code, {"detail": error.detail})

    return _json_response(404, {"detail": "Not found"})


def handler(event: dict[str, Any], _context: object) -> dict[str, object]:
    return asyncio.run(_handle(event))
