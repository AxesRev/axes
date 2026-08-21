"""API Gateway HTTP API (payload 2.0) response helpers."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qs

from integrations.config import settings
from integrations.errors import HttpError


def json_response(status_code: int, payload: object) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def html_response(status_code: int, body: str) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "text/html; charset=utf-8"},
        "body": body,
    }


def text_response(status_code: int, body: str) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "text/plain; charset=utf-8"},
        "body": body,
    }


def redirect(url: str) -> dict[str, object]:
    return {"statusCode": 302, "headers": {"location": url}, "body": ""}


def header(event: dict[str, Any], name: str) -> str | None:
    headers = event.get("headers") or {}
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target and isinstance(value, str):
            return value
    return None


def query_params(event: dict[str, Any]) -> dict[str, str]:
    raw = event.get("queryStringParameters") or {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            result[key] = value
    return result


def form_body(event: dict[str, Any]) -> dict[str, str]:
    body = event.get("body")
    if body is None or body == "":
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    if isinstance(body, bytes):
        body = body.decode()
    parsed = parse_qs(str(body), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def method_and_path(event: dict[str, Any]) -> tuple[str, str]:
    context = event.get("requestContext") or {}
    http = context.get("http") or {}
    method = str(http.get("method") or event.get("httpMethod") or "GET").upper()
    path = str(event.get("rawPath") or event.get("path") or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return method, path


def public_base_url(event: dict[str, Any]) -> str:
    configured = settings.SERVER_URL.strip().rstrip("/")
    if configured:
        return configured
    host = header(event, "host")
    if not host:
        return "http://localhost:8000"
    proto = header(event, "x-forwarded-proto") or "https"
    return f"{proto}://{host}"


def require_tenant_id(params: dict[str, str]) -> str:
    tenant_id = params.get("tenant_id", "").strip()
    if not tenant_id:
        raise HttpError(400, "tenant_id query parameter is required")
    return tenant_id
