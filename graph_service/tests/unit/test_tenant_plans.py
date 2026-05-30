"""Unit tests for tenant fetch plan loading."""

from __future__ import annotations

import pytest

from integrations.tenant_plans import (
    AppIntegrationPlan,
    build_tenant_plans,
    github_installation_id,
    salesforce_org_id,
)


@pytest.mark.unit
def test_build_tenant_plans_groups_integrations() -> None:
    rows = [
        {"tenant_id": "t1", "tenant_name": "Acme", "app_name": "github", "config": {"installation_id": "99"}},
        {"tenant_id": "t1", "tenant_name": "Acme", "app_name": "salesforce", "config": {"org_id": "00Dabc"}},
        {"tenant_id": "t2", "tenant_name": "Beta", "app_name": None, "config": None},
    ]
    plans = build_tenant_plans(rows)  # type: ignore[arg-type]

    assert len(plans) == 2
    assert plans[0].tenant_id == "t1"
    assert len(plans[0].integrations) == 2
    assert plans[0].integrations[0].app_name == "github"
    assert plans[1].tenant_id == "t2"
    assert plans[1].integrations == []


@pytest.mark.unit
def test_github_installation_id_from_config() -> None:
    integration = AppIntegrationPlan(app_name="github", config={"installation_id": "12345"})
    assert github_installation_id(integration) == 12345


@pytest.mark.unit
def test_salesforce_org_id_from_config() -> None:
    integration = AppIntegrationPlan(app_name="salesforce", config={"org_id": "00D000000000001"})
    assert salesforce_org_id(integration) == "00D000000000001"
