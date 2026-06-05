"""Persist GitHub App installations as tenant app_integrations."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_integrations.github.constants import GITHUB_APP_NAME
from app_integrations.github.models import AppIntegration, Tenant

logger = structlog.getLogger(__name__)


def github_integration_config(*, installation_id: str) -> dict[str, str]:
    """Build the JSON config blob for a GitHub App installation."""
    return {"installation_id": installation_id}


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


async def find_github_app_integration_by_installation_id(
    *,
    installation_id: str,
    session: AsyncSession,
) -> AppIntegration | None:
    result = await session.execute(
        select(AppIntegration).where(
            AppIntegration.app_name == GITHUB_APP_NAME,
            AppIntegration.config["installation_id"].astext == installation_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_github_app_integration(
    *,
    tenant_id: str,
    installation_id: str,
    session: AsyncSession,
) -> tuple[Tenant, AppIntegration]:
    """Attach a GitHub App installation to an existing tenant."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise ValueError(f"tenant not found: {tenant_id}")

    normalized_installation_id = installation_id.strip()
    if not normalized_installation_id:
        raise ValueError("installation_id is required")

    existing_for_installation = await find_github_app_integration_by_installation_id(
        installation_id=normalized_installation_id,
        session=session,
    )
    if existing_for_installation is not None and existing_for_installation.tenant_id != tenant_id:
        raise ValueError(
            f"GitHub installation {normalized_installation_id} is already linked to tenant "
            f"{existing_for_installation.tenant_id}"
        )

    integration = await find_github_app_integration_for_tenant(tenant_id=tenant_id, session=session)
    config = github_integration_config(installation_id=normalized_installation_id)

    if integration is not None:
        integration.config = config
        await session.commit()
        logger.info(
            "github_app_integration_updated",
            installation_id=normalized_installation_id,
            tenant_id=tenant_id,
        )
        return tenant, integration

    integration = AppIntegration(
        tenant_id=tenant_id,
        app_name=GITHUB_APP_NAME,
        config=config,
    )
    session.add(integration)
    await session.commit()
    logger.info(
        "github_app_integration_created",
        installation_id=normalized_installation_id,
        tenant_id=tenant_id,
    )
    return tenant, integration
