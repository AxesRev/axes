"""Salesforce package install and JWT org linking."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import quote

import jwt as pyjwt
from simple_salesforce import Salesforce
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.config import settings
from integrations.errors import HttpError
from integrations.http import form_body, html_response, public_base_url, query_params, redirect, require_tenant_id
from integrations.store import get_tenant, upsert_salesforce_app_integration

logger = logging.getLogger(__name__)

_INSTALL_STATE_TTL_SECONDS = 600

_COMPLETE_FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Connect Salesforce</title>
  <style>
    body {{ font-family: sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; margin: 0; background: #f6f8fa; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem 3rem;
             box-shadow: 0 2px 8px rgba(0,0,0,.12); max-width: 28rem; width: 100%; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 0.5rem; }}
    p  {{ color: #57606a; font-size: 0.875rem; }}
    label {{ display: block; margin-top: 1rem; font-size: 0.875rem; font-weight: 600; }}
    input {{ width: 100%; margin-top: 0.25rem; padding: 0.5rem; box-sizing: border-box; }}
    button {{ margin-top: 1.25rem; width: 100%; padding: 0.6rem; background: #0176d3;
              color: white; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; }}
    .error {{ color: #cf222e; font-size: 0.875rem; margin-top: 0.75rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Connect Salesforce org</h1>
    <p>AxesRev is installed. Enter the integration user username (pre-authorized for JWT).</p>
    <form method="post" action="{form_action}">
      <input type="hidden" name="state" value="{state}">
      <label for="integration_username">Integration username</label>
      <input id="integration_username" name="integration_username" type="text"
             placeholder="axes.integration@yourorg.com" required>
      {error_block}
      <button type="submit">Connect org</button>
    </form>
  </div>
</body>
</html>"""

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Salesforce Connected</title>
  <style>
    body {{ font-family: sans-serif; display: flex; justify-content: center;
           align-items: center; height: 100vh; margin: 0; background: #f6f8fa; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem 3rem;
             box-shadow: 0 2px 8px rgba(0,0,0,.12); text-align: center; }}
    h1 {{ color: #2e844a; }}
    p  {{ color: #57606a; }}
    a  {{ color: #0176d3; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>&#10003; Salesforce connected</h1>
    <p>Org <strong>{org_id}</strong> is linked to your tenant.<br>
       <a href="{webapp_url}">Return to Axes</a></p>
  </div>
</body>
</html>"""


def complete_url(event: dict[str, Any]) -> str:
    return f"{public_base_url(event)}/app_integrations/salesforce/complete"


def _require_install_state_secret() -> str:
    secret = settings.install_state_secret
    if not secret:
        raise HttpError(503, "SALESFORCE_INSTALL_STATE_SECRET or GITHUB_INSTALL_STATE_SECRET is required")
    return secret


def _create_state(tenant_id: str, secret: str) -> str:
    return pyjwt.encode(
        {
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(seconds=_INSTALL_STATE_TTL_SECONDS),
        },
        secret,
        algorithm="HS256",
    )


def _decode_state(state: str, secret: str) -> str:
    claims = pyjwt.decode(
        state,
        secret,
        algorithms=["HS256"],
        options={"require": ["tenant_id", "exp"]},
    )
    tenant_id = claims["tenant_id"]
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("state is missing tenant_id")
    return tenant_id


def _form(event: dict[str, Any], state: str, error_block: str = "") -> str:
    return _COMPLETE_FORM_HTML.format(
        form_action=complete_url(event),
        state=escape(state),
        error_block=error_block,
    )


def _make_salesforce_client(*, username: str) -> Salesforce:
    private_key = settings.salesforce_private_key
    if not settings.SALESFORCE_CLIENT_ID or not private_key:
        raise ValueError("SALESFORCE_CLIENT_ID and SALESFORCE_PRIVATE_KEY are required")
    return Salesforce(
        consumer_key=settings.SALESFORCE_CLIENT_ID,
        privatekey=private_key,
        username=username,
        domain=settings.jwt_domain,
    )


def _fetch_organization_id(sf: Salesforce) -> str:
    result: dict[str, Any] = sf.query("SELECT Id FROM Organization LIMIT 1")
    records = result.get("records", [])
    if not records:
        raise ValueError("Organization query returned no rows")
    org_id = records[0].get("Id")
    if not isinstance(org_id, str) or not org_id:
        raise ValueError("Organization Id is missing from API response")
    return org_id


async def salesforce_install(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    tenant_id = require_tenant_id(query_params(event))
    tenant = await get_tenant(session, tenant_id)
    if tenant is None:
        raise HttpError(404, f"tenant not found: {tenant_id}")
    package_version_id = settings.SALESFORCE_PACKAGE_VERSION_ID.strip()
    install_url = f"{settings.package_install_base_url}?p0={quote(package_version_id, safe='')}"
    logger.info("salesforce_package_install_redirect tenant_id=%s", tenant_id)
    return redirect(install_url)


async def salesforce_connect(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    tenant_id = require_tenant_id(query_params(event))
    tenant = await get_tenant(session, tenant_id)
    if tenant is None:
        raise HttpError(404, f"tenant not found: {tenant_id}")
    secret = _require_install_state_secret()
    state = _create_state(tenant_id, secret)
    return redirect(f"{complete_url(event)}?state={quote(state, safe='')}")


def salesforce_complete_form(event: dict[str, Any]) -> dict[str, object]:
    state = query_params(event).get("state", "")
    secret = _require_install_state_secret()
    try:
        _decode_state(state, secret)
    except Exception as exc:
        raise HttpError(400, f"Invalid state: {exc}") from exc
    return html_response(200, _form(event, state))


async def salesforce_complete_submit(event: dict[str, Any], session: AsyncSession) -> dict[str, object]:
    body = form_body(event)
    state = body.get("state", "")
    username = body.get("integration_username", "").strip()
    secret = _require_install_state_secret()
    try:
        tenant_id = _decode_state(state, secret)
    except Exception as exc:
        raise HttpError(400, f"Invalid state: {exc}") from exc

    if not username:
        return html_response(
            400,
            _form(event, state, error_block='<p class="error">Integration username is required.</p>'),
        )

    try:
        sf = _make_salesforce_client(username=username)
        org_id = _fetch_organization_id(sf)
        await upsert_salesforce_app_integration(
            tenant_id=tenant_id,
            org_id=org_id,
            integration_username=username,
            session=session,
        )
    except ValueError as exc:
        logger.warning("salesforce_complete_validation_failed error=%s", exc)
        return html_response(
            400,
            _form(event, state, error_block=f'<p class="error">{escape(str(exc))}</p>'),
        )
    except Exception as exc:
        logger.warning("salesforce_complete_jwt_failed error=%s", exc)
        detail = str(exc).strip() or "unknown Salesforce authentication error"
        return html_response(
            400,
            _form(
                event,
                state,
                error_block=f'<p class="error">Salesforce authentication failed: {escape(detail)}</p>',
            ),
        )

    logger.info("salesforce_complete_success tenant_id=%s org_id=%s", tenant_id, org_id)
    return html_response(
        200,
        _SUCCESS_HTML.format(org_id=escape(org_id), webapp_url=escape(settings.WEBAPP_URL.rstrip("/"))),
    )
