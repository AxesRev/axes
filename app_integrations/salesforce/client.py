"""JWT Salesforce client for verifying integration users after package install."""

from __future__ import annotations

from typing import Any

from simple_salesforce import Salesforce

from app_integrations.salesforce.settings import SalesforceIntegrationSettings, salesforce_settings


def make_salesforce_client(
    *,
    username: str,
    settings: SalesforceIntegrationSettings | None = None,
) -> Salesforce:
    """Create a JWT-authenticated Salesforce REST client."""
    config = settings or salesforce_settings
    private_key = config.private_key
    if not config.SALESFORCE_CLIENT_ID or not private_key:
        raise ValueError("SALESFORCE_CLIENT_ID and SALESFORCE_PRIVATE_KEY_PATH are required")
    return Salesforce(
        consumer_key=config.SALESFORCE_CLIENT_ID,
        privatekey=private_key,
        username=username,
        domain=config.jwt_domain,
    )


def fetch_organization_id(sf: Salesforce) -> str:
    """Return the org Id for the authenticated integration user."""
    result: dict[str, Any] = sf.query("SELECT Id FROM Organization LIMIT 1")
    records = result.get("records", [])
    if not records:
        raise ValueError("Organization query returned no rows")
    org_id = records[0].get("Id")
    if not isinstance(org_id, str) or not org_id:
        raise ValueError("Organization Id is missing from API response")
    return org_id
