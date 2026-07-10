"""Persist Slack workspace installs as tenant app_integrations."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.slack.constants import SLACK_APP_NAME
from tenant.models import AppIntegration, Tenant, UserIdentity

logger = structlog.getLogger(__name__)


def slack_integration_config(*, team_id: str) -> dict[str, str]:
    """Build the JSON config blob for a Slack workspace integration."""
    return {"team_id": team_id}


async def find_slack_app_integration(
    *,
    team_id: str,
    session: AsyncSession,
) -> AppIntegration | None:
    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.app_name == SLACK_APP_NAME,
            AppIntegration.config["team_id"].astext == team_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_slack_app_integration(
    *,
    tenant_id: str,
    team_id: str,
    team_name: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    """Attach a Slack workspace install to an existing tenant."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise ValueError(f"tenant not found: {tenant_id}")

    integration = await find_slack_app_integration(team_id=team_id, session=session)
    config = slack_integration_config(team_id=team_id)

    if integration is not None:
        if integration.tenant_id != tenant_id:
            raise ValueError(f"Slack team {team_id} is already linked to tenant {integration.tenant_id}")
        integration.config = config
        await session.commit()
        logger.info("slack_app_integration_updated", team_id=team_id, tenant_id=tenant_id)
        return tenant, integration

    integration = AppIntegration(
        tenant_id=tenant_id,
        app_name=SLACK_APP_NAME,
        config=config,
    )
    session.add(integration)
    await session.commit()
    logger.info(
        "slack_app_integration_created",
        team_id=team_id,
        team_name=team_name,
        tenant_id=tenant_id,
    )
    return tenant, integration


async def get_or_create_slack_user_identity_for_team(
    *,
    slack_user_id: str,
    team_id: str,
    session: AsyncSession,
) -> UserIdentity | None:
    """Get or create a Slack user identity scoped to the tenant that owns *team_id*."""
    integration = await find_slack_app_integration(team_id=team_id, session=session)
    if integration is None:
        return None

    tenant_id = integration.tenant_id
    result = await session.execute(select(UserIdentity).where(UserIdentity.slack_user_id == slack_user_id))
    identity = result.scalar_one_or_none()
    if identity is not None:
        return identity

    identity = UserIdentity(slack_user_id=slack_user_id, tenant_id=tenant_id)
    session.add(identity)
    await session.commit()
    logger.info(
        "slack_user_identity_created",
        slack_user_id=slack_user_id,
        team_id=team_id,
        tenant_id=tenant_id,
    )
    return identity
