"""FastAPI routes for AxesRev managed package install and tenant linking."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from app_integrations.salesforce.client import fetch_organization_id, make_salesforce_client
from app_integrations.salesforce.install_state import (
    create_salesforce_install_state,
    decode_salesforce_install_state,
)
from app_integrations.salesforce.service import upsert_salesforce_app_integration
from app_integrations.salesforce.settings import salesforce_settings
from tenant.models import Tenant

logger = structlog.getLogger(__name__)

router = APIRouter(prefix="/auth/salesforce", tags=["salesforce"])

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


def _require_install_state_secret() -> str:
    secret = salesforce_settings.install_state_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SALESFORCE_INSTALL_STATE_SECRET or GITHUB_INSTALL_STATE_SECRET is required",
        )
    return secret


@router.get("/install", response_model=None)
async def salesforce_package_install(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Redirect to Salesforce managed package install for this tenant."""
    package_version_id = salesforce_settings.SALESFORCE_PACKAGE_VERSION_ID.strip()

    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant not found: {tenant_id}")

    # Salesforce blocks retURL to external sites; connect step is separate (/connect).
    install_url = f"{salesforce_settings.package_install_base_url}?p0={quote(package_version_id, safe='')}"
    logger.info("salesforce_package_install_redirect", tenant_id=tenant_id)
    return RedirectResponse(url=install_url, status_code=status.HTTP_302_FOUND)


@router.get("/connect", response_model=None)
async def salesforce_connect_start(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """After package install in Salesforce, open the integration-user connect form."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant not found: {tenant_id}")

    secret = _require_install_state_secret()
    state = create_salesforce_install_state(tenant_id=tenant_id, secret=secret)
    complete_url = (
        f"{salesforce_settings.SERVER_URL.rstrip('/')}/auth/salesforce/complete?state={quote(state, safe='')}"
    )
    return RedirectResponse(url=complete_url, status_code=status.HTTP_302_FOUND)


@router.get("/complete", response_class=HTMLResponse)
async def salesforce_complete_form(state: str) -> HTMLResponse:
    """Show form to link installed org via integration user JWT."""
    secret = _require_install_state_secret()
    try:
        decode_salesforce_install_state(state, secret)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state: {exc}",
        ) from exc

    form_action = f"{salesforce_settings.SERVER_URL.rstrip('/')}/auth/salesforce/complete"
    return HTMLResponse(
        content=_COMPLETE_FORM_HTML.format(
            form_action=form_action,
            state=escape(state),
            error_block="",
        ),
        status_code=status.HTTP_200_OK,
    )


@router.post("/complete", response_class=HTMLResponse)
async def salesforce_complete_submit(
    state: str = Form(...),
    integration_username: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Verify JWT access for the integration user and persist org_id on the tenant."""
    secret = _require_install_state_secret()
    try:
        tenant_id = decode_salesforce_install_state(state, secret)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state: {exc}",
        ) from exc

    username = integration_username.strip()
    if not username:
        form_action = f"{salesforce_settings.SERVER_URL.rstrip('/')}/auth/salesforce/complete"
        return HTMLResponse(
            content=_COMPLETE_FORM_HTML.format(
                form_action=form_action,
                state=escape(state),
                error_block='<p class="error">Integration username is required.</p>',
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        sf = make_salesforce_client(username=username)
        org_id = fetch_organization_id(sf)
        await upsert_salesforce_app_integration(
            tenant_id=tenant_id,
            org_id=org_id,
            integration_username=username,
            session=session,
        )
    except ValueError as exc:
        logger.warning("salesforce_complete_validation_failed", error=str(exc))
        form_action = f"{salesforce_settings.SERVER_URL.rstrip('/')}/auth/salesforce/complete"
        return HTMLResponse(
            content=_COMPLETE_FORM_HTML.format(
                form_action=form_action,
                state=escape(state),
                error_block=f'<p class="error">{escape(str(exc))}</p>',
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.warning("salesforce_complete_jwt_failed", error=str(exc))
        form_action = f"{salesforce_settings.SERVER_URL.rstrip('/')}/auth/salesforce/complete"
        detail = str(exc).strip() or "unknown Salesforce authentication error"
        return HTMLResponse(
            content=_COMPLETE_FORM_HTML.format(
                form_action=form_action,
                state=escape(state),
                error_block=f'<p class="error">Salesforce authentication failed: {escape(detail)}</p>',
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    logger.info("salesforce_complete_success", tenant_id=tenant_id, org_id=org_id)
    return HTMLResponse(
        content=_SUCCESS_HTML.format(
            org_id=escape(org_id),
            webapp_url=escape(salesforce_settings.WEBAPP_URL.rstrip("/")),
        ),
        status_code=status.HTTP_200_OK,
    )
