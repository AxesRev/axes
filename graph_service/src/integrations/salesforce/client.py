from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceMalformedRequest

from integrations.salesforce.settings import SalesforceAppSettings, get_salesforce_settings

logger = logging.getLogger(__name__)


def make_salesforce_client(
    *,
    username: str,
    settings: SalesforceAppSettings | None = None,
) -> Salesforce:
    """Create a JWT-authenticated Salesforce REST client."""
    config = settings or get_salesforce_settings()
    return Salesforce(
        consumer_key=config.SALESFORCE_CLIENT_ID,
        privatekey=config.private_key,
        username=username,
        domain=config.jwt_domain,
    )


def query_all(sf: Salesforce, soql: str) -> list[dict[str, Any]]:
    """Run SOQL and return all records, following pagination."""
    result = sf.query(soql)
    records: list[dict[str, Any]] = list(result.get("records", []))
    while not result.get("done", True) and result.get("nextRecordsUrl"):
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)
        records.extend(result.get("records", []))
    return records


def query_all_or_empty(sf: Salesforce, soql: str, *, context: str) -> list[dict[str, Any]]:
    """Run SOQL and return records, or an empty list when the query is unsupported."""
    try:
        return query_all(sf, soql)
    except SalesforceMalformedRequest as exc:
        logger.warning("optional_soql_skipped context=%s error=%s", context, exc)
        return []


def query_batches(sf: Salesforce, soql: str, *, batch_size: int = 2000) -> Iterator[list[dict[str, Any]]]:
    """Yield SOQL result pages."""
    result = sf.query(soql)
    while True:
        records = list(result.get("records", []))
        for start in range(0, len(records), batch_size):
            yield records[start : start + batch_size]
        if result.get("done", True) or not result.get("nextRecordsUrl"):
            break
        result = sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)


def describe_global(sf: Salesforce) -> list[dict[str, Any]]:
    """Return sobject describe summaries from the org."""
    payload = sf.describe()
    return list(payload.get("sobjects", []))
