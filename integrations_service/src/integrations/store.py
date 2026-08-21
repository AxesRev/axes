"""Persist Slack, GitHub, and Salesforce installs as tenant app_integrations."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import AppIntegration, OAuthState, Tenant, UserIdentity

logger = logging.getLogger(__name__)

SLACK_APP_NAME = "slack"
GITHUB_APP_NAME = "github"
SALESFORCE_APP_NAME = "salesforce"


async def get_tenant(session: AsyncSession, tenant_id: str) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def upsert_slack_app_integration(
    *,
    tenant_id: str,
    team_id: str,
    team_name: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    tenant = await get_tenant(session, tenant_id)
    if tenant is None:
        raise ValueError(f"tenant not found: {tenant_id}")

    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.app_name == SLACK_APP_NAME,
            AppIntegration.config["team_id"].astext == team_id,
        )
    )
    integration = result.scalar_one_or_none()
    config = {"team_id": team_id}

    if integration is not None:
        if integration.tenant_id != tenant_id:
            raise ValueError(f"Slack team {team_id} is already linked to tenant {integration.tenant_id}")
        integration.config = config
        await session.commit()
        logger.info("slack_app_integration_updated team_id=%s tenant_id=%s", team_id, tenant_id)
        return tenant, integration

    integration = AppIntegration(tenant_id=tenant_id, app_name=SLACK_APP_NAME, config=config)
    session.add(integration)
    await session.commit()
    logger.info(
        "slack_app_integration_created team_id=%s team_name=%s tenant_id=%s",
        team_id,
        team_name,
        tenant_id,
    )
    return tenant, integration


async def find_github_app_integration_for_tenant(
    *,
    tenant_id: str,
    session: AsyncSession,
) -> AppIntegration | None:
    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.tenant_id == tenant_id,
            AppIntegration.app_name == GITHUB_APP_NAME,
        )
    )
    return result.scalar_one_or_none()


async def upsert_github_app_integration(
    *,
    tenant_id: str,
    installation_id: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    tenant = await get_tenant(session, tenant_id)
    if tenant is None:
        raise ValueError(f"tenant not found: {tenant_id}")

    normalized_installation_id = installation_id.strip()
    if not normalized_installation_id:
        raise ValueError("installation_id is required")

    existing_for_installation = (
        await session.execute(
            select(AppIntegration).where(
                AppIntegration.app_name == GITHUB_APP_NAME,
                AppIntegration.config["installation_id"].astext == normalized_installation_id,
            )
        )
    ).scalar_one_or_none()
    if existing_for_installation is not None and existing_for_installation.tenant_id != tenant_id:
        raise ValueError(
            f"GitHub installation {normalized_installation_id} is already linked to tenant "
            f"{existing_for_installation.tenant_id}"
        )

    integration = await find_github_app_integration_for_tenant(tenant_id=tenant_id, session=session)
    config = {"installation_id": normalized_installation_id}

    if integration is not None:
        integration.config = config
        await session.commit()
        logger.info(
            "github_app_integration_updated installation_id=%s tenant_id=%s",
            normalized_installation_id,
            tenant_id,
        )
        return tenant, integration

    integration = AppIntegration(tenant_id=tenant_id, app_name=GITHUB_APP_NAME, config=config)
    session.add(integration)
    await session.commit()
    logger.info(
        "github_app_integration_created installation_id=%s tenant_id=%s",
        normalized_installation_id,
        tenant_id,
    )
    return tenant, integration


def set_github_extra(identity: UserIdentity, *, user_id: str, email: str) -> None:
    extra: dict[str, Any] = dict(identity.extra_app_data or {})
    extra["github"] = {"user_id": user_id, "email": email}
    identity.extra_app_data = extra


async def link_github_identity(
    *,
    slack_user_id: str,
    github_user_id: str,
    github_email: str,
    oauth_token: str,
    session: AsyncSession,
) -> UserIdentity:
    result = await session.execute(select(UserIdentity).where(UserIdentity.slack_user_id == slack_user_id))
    identity = result.scalar_one_or_none()
    if identity is None:
        raise ValueError(f"user identity not found for slack_user_id={slack_user_id}")

    set_github_extra(identity, user_id=github_user_id, email=github_email)

    state_result = await session.execute(select(OAuthState).where(OAuthState.token == oauth_token))
    state_record = state_result.scalar_one_or_none()
    if state_record is not None:
        await session.delete(state_record)

    await session.commit()
    logger.info(
        "github_identity_linked slack_user_id=%s github_user_id=%s tenant_id=%s",
        slack_user_id,
        github_user_id,
        identity.tenant_id,
    )
    return identity


async def upsert_salesforce_app_integration(
    *,
    tenant_id: str,
    org_id: str,
    integration_username: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    tenant = await get_tenant(session, tenant_id)
    if tenant is None:
        raise ValueError(f"tenant not found: {tenant_id}")

    normalized_org_id = org_id.strip()
    normalized_username = integration_username.strip()
    if not normalized_org_id:
        raise ValueError("org_id is required")
    if not normalized_username:
        raise ValueError("integration_username is required")

    existing_for_org = (
        await session.execute(
            select(AppIntegration).where(
                AppIntegration.app_name == SALESFORCE_APP_NAME,
                AppIntegration.config["org_id"].astext == normalized_org_id,
            )
        )
    ).scalar_one_or_none()
    if existing_for_org is not None and existing_for_org.tenant_id != tenant_id:
        raise ValueError(f"Salesforce org {normalized_org_id} is already linked to tenant {existing_for_org.tenant_id}")

    integration = (
        await session.execute(
            select(AppIntegration).where(
                AppIntegration.tenant_id == tenant_id,
                AppIntegration.app_name == SALESFORCE_APP_NAME,
            )
        )
    ).scalar_one_or_none()
    config = {"org_id": normalized_org_id, "integration_username": normalized_username}

    if integration is not None:
        integration.config = config
        await session.commit()
        logger.info("salesforce_app_integration_updated org_id=%s tenant_id=%s", normalized_org_id, tenant_id)
        return tenant, integration

    integration = AppIntegration(tenant_id=tenant_id, app_name=SALESFORCE_APP_NAME, config=config)
    session.add(integration)
    await session.commit()
    logger.info("salesforce_app_integration_created org_id=%s tenant_id=%s", normalized_org_id, tenant_id)
    return tenant, integration
