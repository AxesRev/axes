"""Custom Bolt installation store that persists team installs to app_integrations."""

from __future__ import annotations

import logging

from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore
from slack_sdk.oauth.installation_store.models.bot import Bot
from slack_sdk.oauth.installation_store.models.installation import Installation

from aegra_api.core.orm import get_session
from app_integrations.slack.service import upsert_slack_app_integration
from slack_app.config import slack_settings

logger = logging.getLogger(__name__)


class AxesInstallationStore(AsyncInstallationStore):
    """Saves Slack workspace installs as tenant app_integrations rows."""

    async def async_save(
        self,
        installation: Installation,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        team_id: str = installation.team_id or ""
        team_name: str = installation.team_name or team_id
        tenant_id: str | None = installation.custom_values.get("tenant_id")
        if not team_id:
            (logger or logging.getLogger(__name__)).warning("slack_installation_missing_team_id; skipping save")
            return
        if not tenant_id:
            (logger or logging.getLogger(__name__)).warning("slack_installation_missing_tenant_id; skipping save")
            return
        async for session in get_session():
            await upsert_slack_app_integration(
                tenant_id=tenant_id,
                team_id=team_id,
                team_name=team_name,
                session=session,
            )

    async def async_find_installation(
        self,
        *,
        enterprise_id: str | None,
        team_id: str | None,
        is_enterprise_install: bool | None = False,
        app_id: str | None = None,
    ) -> Installation | None:
        return None

    async def async_find_bot(
        self,
        *,
        enterprise_id: str | None,
        team_id: str | None,
        is_enterprise_install: bool | None = False,
        app_id: str | None = None,
    ) -> Bot | None:
        token: str = slack_settings.SLACK_BOT_TOKEN
        if not token:
            return None
        return Bot(
            app_id=app_id or "",
            enterprise_id=enterprise_id,
            team_id=team_id or "",
            bot_token=token,
            bot_id="",
            bot_user_id="",
            installed_at=0.0,
        )

    async def async_delete_installation(
        self,
        *,
        enterprise_id: str | None,
        team_id: str | None,
        user_id: str | None = None,
    ) -> None:
        pass

    async def async_delete_all(
        self,
        *,
        enterprise_id: str | None,
        team_id: str | None,
    ) -> None:
        pass
