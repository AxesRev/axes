"""FastAPI router for tenant-scoped GitHub App installation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.orm import get_session
from app_integrations.github.models import Tenant
from app_integrations.github.service import upsert_github_app_integration
from app_integrations.github.settings import github_settings

logger = structlog.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["github-app"])
_INSTALL_STATE_TTL_SECONDS = 600

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>GitHub App Installed</title>
  <style>
    body {{ font-family: sans-serif; display: flex; justify-content: center;
           align-items: center; height: 100vh; margin: 0; background: #f6f8fa; }}
    .card {{ background: white; border-radius: 8px; padding: 2rem 3rem;
             box-shadow: 0 2px 8px rgba(0,0,0,.12); text-align: center; }}
    h1 {{ color: #2da44e; }}
    p  {{ color: #57606a; }}
    a  {{ color: #0969da; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>&#10003; GitHub App installed</h1>
    <p>Installation <strong>#{installation_id}</strong> has been connected to your tenant.<br>
       <a href="{webapp_url}">Return to Axes</a></p>
  </div>
</body>
</html>"""


@router.get("/install")
async def github_app_install_start(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Validate *tenant_id* and redirect the browser to GitHub's install page."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant not found: {tenant_id}")

    if not github_settings.GITHUB_APP_SLUG:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_APP_SLUG is not configured on this server.",
        )
    if not github_settings.GITHUB_INSTALL_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_INSTALL_STATE_SECRET is not configured.",
        )

    state = pyjwt.encode(
        {
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) + timedelta(seconds=_INSTALL_STATE_TTL_SECONDS),
        },
        github_settings.GITHUB_INSTALL_STATE_SECRET,
        algorithm="HS256",
        headers={"typ": "JWT"},
    )
    install_url = f"https://github.com/apps/{github_settings.GITHUB_APP_SLUG}/installations/new?state={state}"
    logger.info("github_app_install_redirect", tenant_id=tenant_id)
    return RedirectResponse(url=install_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def github_app_install_callback(
    installation_id: str,
    state: str | None = None,
    setup_action: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Handle GitHub's post-install redirect and persist the installation for a tenant."""
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter. Start installation from the Axes webapp.",
        )
    if not github_settings.GITHUB_INSTALL_STATE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_INSTALL_STATE_SECRET is not configured.",
        )

    try:
        claims = pyjwt.decode(
            state,
            github_settings.GITHUB_INSTALL_STATE_SECRET,
            algorithms=["HS256"],
            options={"require": ["tenant_id", "exp"]},
        )
        tenant_id = claims["tenant_id"]
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("state is missing tenant_id")
    except (pyjwt.PyJWTError, ValueError) as exc:
        logger.warning("github_app_install_invalid_state", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid installation state: {exc}",
        ) from exc

    try:
        await upsert_github_app_integration(
            tenant_id=tenant_id,
            installation_id=installation_id,
            session=session,
        )
    except ValueError as exc:
        logger.warning(
            "github_app_install_persist_failed",
            tenant_id=tenant_id,
            installation_id=installation_id,
            error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info(
        "github_app_install_complete",
        tenant_id=tenant_id,
        installation_id=installation_id,
        setup_action=setup_action,
    )
    return HTMLResponse(
        content=_SUCCESS_HTML.format(
            installation_id=installation_id,
            webapp_url=github_settings.WEBAPP_URL.rstrip("/"),
        ),
        status_code=status.HTTP_200_OK,
    )
