"""Persist Salesforce org connections as tenant app_integrations."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.salesforce.constants import SALESFORCE_APP_NAME
from tenant.models import AppIntegration, Tenant

logger = structlog.getLogger(__name__)


def salesforce_integration_config(*, org_id: str, integration_username: str) -> dict[str, str]:
    """Build the JSON config blob for a Salesforce org connection."""
    return {
        "org_id": org_id,
        "integration_username": integration_username,
    }


async def find_salesforce_app_integration_for_tenant(
    *,
    tenant_id: str,
    session: AsyncSession,
) -> AppIntegration | None:
    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.tenant_id == tenant_id,
            AppIntegration.app_name == SALESFORCE_APP_NAME,
        )
    )
    return result.scalar_one_or_none()


async def find_salesforce_app_integration_by_org_id(
    *,
    org_id: str,
    session: AsyncSession,
) -> AppIntegration | None:
    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.app_name == SALESFORCE_APP_NAME,
            AppIntegration.config["org_id"].astext == org_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_salesforce_app_integration(
    *,
    tenant_id: str,
    org_id: str,
    integration_username: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    """Attach a Salesforce org to an existing tenant."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise ValueError(f"tenant not found: {tenant_id}")

    normalized_org_id = org_id.strip()
    normalized_username = integration_username.strip()
    if not normalized_org_id:
        raise ValueError("org_id is required")
    if not normalized_username:
        raise ValueError("integration_username is required")

    existing_for_org = await find_salesforce_app_integration_by_org_id(
        org_id=normalized_org_id,
        session=session,
    )
    if existing_for_org is not None and existing_for_org.tenant_id != tenant_id:
        raise ValueError(f"Salesforce org {normalized_org_id} is already linked to tenant {existing_for_org.tenant_id}")

    integration = await find_salesforce_app_integration_for_tenant(tenant_id=tenant_id, session=session)
    config = salesforce_integration_config(
        org_id=normalized_org_id,
        integration_username=normalized_username,
    )

    if integration is not None:
        integration.config = config
        await session.commit()
        logger.info(
            "salesforce_app_integration_updated",
            org_id=normalized_org_id,
            tenant_id=tenant_id,
        )
        return tenant, integration

    integration = AppIntegration(
        tenant_id=tenant_id,
        app_name=SALESFORCE_APP_NAME,
        config=config,
    )
    session.add(integration)
    await session.commit()
    logger.info(
        "salesforce_app_integration_created",
        org_id=normalized_org_id,
        tenant_id=tenant_id,
    )
    return tenant, integration
