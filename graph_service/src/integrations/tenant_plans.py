"""Load per-tenant fetch plans from Postgres ``tenants`` and ``app_integrations``."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from integrations.github.settings import get_runner_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppIntegrationPlan:
    """One ``app_integrations`` row to drive ingestion."""

    app_name: str
    config: dict[str, Any]


@dataclass
class TenantFetchPlan:
    """Tenant plus all configured app integrations."""

    tenant_id: str
    tenant_name: str
    integrations: list[AppIntegrationPlan] = field(default_factory=list)


def _parse_config(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _config_str(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_tenant_plans(rows: list[asyncpg.Record]) -> list[TenantFetchPlan]:
    """Group flat SQL rows into ``TenantFetchPlan`` instances."""
    by_id: dict[str, TenantFetchPlan] = {}
    order: list[str] = []

    for row in rows:
        tenant_id = str(row["tenant_id"])
        if tenant_id not in by_id:
            by_id[tenant_id] = TenantFetchPlan(
                tenant_id=tenant_id,
                tenant_name=str(row["tenant_name"]),
            )
            order.append(tenant_id)

        app_name = row["app_name"]
        if app_name is None:
            continue

        by_id[tenant_id].integrations.append(
            AppIntegrationPlan(app_name=str(app_name), config=_parse_config(row["config"]))
        )

    return [by_id[tid] for tid in order]


async def load_tenant_fetch_plans() -> list[TenantFetchPlan]:
    """Load every tenant and its ``app_integrations`` from the metadata database."""
    runner = get_runner_settings()
    query = """
        SELECT
            t.id AS tenant_id,
            t.name AS tenant_name,
            ai.app_name AS app_name,
            ai.config AS config
        FROM tenants t
        LEFT JOIN app_integrations ai ON ai.tenant_id = t.id
        ORDER BY t.name, ai.app_name
    """
    conn = await asyncpg.connect(dsn=runner.postgres_url)
    try:
        rows = await conn.fetch(query)
    finally:
        await conn.close()

    plans = build_tenant_plans(rows)
    logger.info("loaded_tenant_fetch_plans tenant_count=%s", len(plans))
    return plans


def github_installation_id(integration: AppIntegrationPlan) -> int | None:
    """Parse GitHub App ``installation_id`` from integration config."""
    raw = _config_str(integration.config, "installation_id")
    if raw is None:
        return None
    return int(raw)


def salesforce_org_id(integration: AppIntegrationPlan) -> str | None:
    return _config_str(integration.config, "org_id")


def salesforce_integration_username(integration: AppIntegrationPlan) -> str | None:
    return _config_str(integration.config, "integration_username") or _config_str(integration.config, "username")
