"""API Gateway HTTP API (payload 2.0) Lambda handler for tenant dashboard routes."""

from __future__ import annotations

import base64
import json
from typing import Any

from common.lambda_async import run as run_async
from tenants.auth import claims_from_bearer
from tenants.db import session_scope
from tenants.errors import HttpError
from tenants.routes import get_my_agent_context, get_my_integrations, get_my_tenant, update_my_agent_context


def _json_response(status_code: int, payload: object) -> dict[str, object]:
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


def _method_and_path(event: dict[str, Any]) -> tuple[str, str]:
    context = event.get("requestContext") or {}
    http = context.get("http") or {}
    method = str(http.get("method") or event.get("httpMethod") or "GET").upper()
    path = str(event.get("rawPath") or event.get("path") or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return method, path


def _json_body(event: dict[str, Any]) -> dict[str, object]:
    body = event.get("body")
    if body is None or body == "":
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    if isinstance(body, bytes):
        body = body.decode()
    try:
        payload = json.loads(str(body))
    except ValueError as error:
        raise HttpError(400, "Invalid JSON body") from error
    if not isinstance(payload, dict):
        raise HttpError(400, "Invalid JSON body")
    return payload


async def _with_session():
    return session_scope()


async def _handle(event: dict[str, Any]) -> dict[str, object]:
    method, path = _method_and_path(event)
    try:
        if method == "GET" and path == "/tenants/me":
            claims = claims_from_bearer(_header(event, "authorization"))
            async with await _with_session() as session:
                payload = await get_my_tenant(claims=claims, session=session)
            return _json_response(200, payload)

        if method == "GET" and path == "/tenants/me/integrations":
            claims = claims_from_bearer(_header(event, "authorization"))
            async with await _with_session() as session:
                payload = await get_my_integrations(claims=claims, session=session)
            return _json_response(200, payload)

        if method == "GET" and path == "/tenants/me/agent-context":
            claims = claims_from_bearer(_header(event, "authorization"))
            async with await _with_session() as session:
                payload = await get_my_agent_context(claims=claims, session=session)
            return _json_response(200, payload)

        if method == "PUT" and path == "/tenants/me/agent-context":
            claims = claims_from_bearer(_header(event, "authorization"))
            body = _json_body(event)
            content = body.get("content")
            if not isinstance(content, str):
                raise HttpError(422, "content is required")
            async with await _with_session() as session:
                payload = await update_my_agent_context(claims=claims, content=content, session=session)
            return _json_response(200, payload)
    except HttpError as error:
        return _json_response(error.status_code, {"detail": error.detail})

    return _json_response(404, {"detail": "Not found"})


def handler(event: dict[str, Any], _context: object) -> dict[str, object]:
    return run_async(_handle(event))
