"""Slack OAuth flow that requires a pre-registered tenant_id at install time."""

from __future__ import annotations

from slack_bolt.error import BoltError
from slack_bolt.oauth.async_oauth_flow import AsyncOAuthFlow
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_bolt.response import BoltResponse
from slack_sdk.oauth.installation_store import Installation
from sqlalchemy import select

from aegra_api.core.orm import get_session
from app_integrations.github.models import Tenant
from app_integrations.slack.state_store import TenantOAuthStateStore


class TenantAsyncOAuthFlow(AsyncOAuthFlow):
    """Starts Slack install only when ``tenant_id`` is present and valid."""

    async def handle_installation(self, request: AsyncBoltRequest) -> BoltResponse:
        tenant_ids = request.query.get("tenant_id")
        tenant_id = tenant_ids[0] if tenant_ids else None
        if not tenant_id:
            return BoltResponse(
                status=400,
                body="tenant_id query parameter is required",
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )

        async for session in get_session():
            result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalar_one_or_none()

        if tenant is None:
            return BoltResponse(
                status=404,
                body=f"tenant not found: {tenant_id}",
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )

        set_cookie_value: str | None = None
        state = ""
        url = await self.build_authorize_url(state, request)
        if self.settings.state_validation_enabled is True:
            state_store = self.settings.state_store
            if not isinstance(state_store, TenantOAuthStateStore):
                raise BoltError("TenantAsyncOAuthFlow requires TenantOAuthStateStore")
            state = await state_store.async_issue(tenant_id=tenant_id)
            url = await self.build_authorize_url(state, request)
            set_cookie_value = self.settings.state_utils.build_set_cookie_for_new_state(state)

        if self.settings.install_page_rendering_enabled:
            html = await self.build_install_page_html(url, request)
            return BoltResponse(
                status=200,
                body=html,
                headers=await self.append_set_cookie_headers(
                    {"Content-Type": "text/html; charset=utf-8"},
                    set_cookie_value,
                ),
            )
        return BoltResponse(
            status=302,
            body="",
            headers=await self.append_set_cookie_headers(
                {"Content-Type": "text/html; charset=utf-8", "Location": url},
                set_cookie_value,
            ),
        )

    async def store_installation(self, request: AsyncBoltRequest, installation: Installation) -> None:
        state_values = request.query.get("state")
        state = state_values[0] if state_values else None
        tenant_id: str | None = None
        if state is not None:
            state_store = self.settings.state_store
            if isinstance(state_store, TenantOAuthStateStore):
                tenant_id = state_store.pop_tenant_id(state)
        if not tenant_id:
            raise BoltError("Slack install is missing tenant_id from OAuth state")
        installation.custom_values["tenant_id"] = tenant_id
        await self.settings.installation_store.async_save(installation)
