"""Run graph ingestion per tenant using ``app_integrations`` configuration."""

from __future__ import annotations

import logging

from integrations.app_names import GITHUB_APP_NAME, SALESFORCE_APP_NAME, SLACK_APP_NAME
from integrations.github.ingestion.installation import fetch_installation
from integrations.salesforce.run import run_salesforce_ingestion
from integrations.tenant_plans import (
    AppIntegrationPlan,
    TenantFetchPlan,
    github_installation_id,
    load_tenant_fetch_plans,
    salesforce_fetch_credentials,
)

logger = logging.getLogger(__name__)


async def fetch_tenant(plan: TenantFetchPlan) -> None:
    """Ingest graph data for each app integration configured on a tenant."""
    if not plan.integrations:
        logger.info("tenant_fetch_skipped_no_integrations tenant_id=%s name=%s", plan.tenant_id, plan.tenant_name)
        return

    logger.info(
        "tenant_fetch_start tenant_id=%s name=%s apps=%s",
        plan.tenant_id,
        plan.tenant_name,
        [integration.app_name for integration in plan.integrations],
    )

    for integration in plan.integrations:
        if integration.app_name == GITHUB_APP_NAME:
            await _fetch_github_integration(plan, integration)
        elif integration.app_name == SALESFORCE_APP_NAME:
            await _fetch_salesforce_integration(plan, integration)
        elif integration.app_name == SLACK_APP_NAME:
            logger.debug(
                "tenant_fetch_skip_slack_no_graph_ingest tenant_id=%s",
                plan.tenant_id,
            )
        else:
            logger.warning(
                "tenant_fetch_unknown_app tenant_id=%s app_name=%s",
                plan.tenant_id,
                integration.app_name,
            )

    logger.info("tenant_fetch_complete tenant_id=%s", plan.tenant_id)


async def _fetch_github_integration(plan: TenantFetchPlan, integration: AppIntegrationPlan) -> None:
    installation_id = github_installation_id(integration)
    if installation_id is None:
        logger.warning(
            "github_fetch_skipped_missing_installation_id tenant_id=%s",
            plan.tenant_id,
        )
        return

    logger.info(
        "github_fetch_start tenant_id=%s installation_id=%s",
        plan.tenant_id,
        installation_id,
    )
    await fetch_installation(
        installation_id,
        tenant_id=plan.tenant_id,
        tenant_name=plan.tenant_name,
    )
    logger.info(
        "github_fetch_complete tenant_id=%s installation_id=%s",
        plan.tenant_id,
        installation_id,
    )


async def _fetch_salesforce_integration(plan: TenantFetchPlan, integration: AppIntegrationPlan) -> None:
    credentials = salesforce_fetch_credentials(integration)
    if credentials is None:
        logger.warning(
            "salesforce_fetch_skipped_incomplete_app_integration tenant_id=%s "
            "(connect Salesforce in the webapp to set org_id and integration_username)",
            plan.tenant_id,
        )
        return

    org_id, username = credentials
    logger.info(
        "salesforce_fetch_start tenant_id=%s org_id=%s username=%s",
        plan.tenant_id,
        org_id,
        username,
    )
    await run_salesforce_ingestion(
        tenant_id=plan.tenant_id,
        tenant_name=plan.tenant_name,
        org_id=org_id,
        integration_username=username,
        skip_record_access=False,
    )


async def fetch_all_tenants() -> None:
    """Load tenants from Postgres and ingest each tenant's configured apps."""
    plans = await load_tenant_fetch_plans()
    if not plans:
        logger.error("no_tenants_in_database")
        raise SystemExit(1)

    for plan in plans:
        await fetch_tenant(plan)
