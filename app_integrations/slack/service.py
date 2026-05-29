"""Persist Slack workspace installs as tenant app_integrations."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.github.models import AppIntegration, Tenant
from app_integrations.slack.constants import SLACK_APP_NAME

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
    team_id: str,
    team_name: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    """Create or update the Slack ``app_integrations`` row for a workspace install."""
    integration = await find_slack_app_integration(team_id=team_id, session=session)
    config = slack_integration_config(team_id=team_id)

    if integration is not None:
        integration.config = config
        result = await session.execute(select(Tenant).where(Tenant.id == integration.tenant_id))
        tenant = result.scalar_one()
        tenant.name = team_name
        await session.commit()
        logger.info("slack_app_integration_updated", team_id=team_id, tenant_id=tenant.id)
        return tenant, integration

    tenant = Tenant(name=team_name)
    session.add(tenant)
    await session.flush()

    integration = AppIntegration(
        tenant_id=tenant.id,
        app_name=SLACK_APP_NAME,
        config=config,
    )
    session.add(integration)
    await session.commit()
    logger.info("slack_app_integration_created", team_id=team_id, tenant_id=tenant.id)
    return tenant, integration
