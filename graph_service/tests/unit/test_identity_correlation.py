"""Unit tests for AppIdentity → Identity correlation by email."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from integrations.identity_correlation import (
    correlate_app_identities_by_email,
    correlation_row_from_email,
    normalize_email,
)
from integrations.salesforce.ingestion.users import email_from_user


@pytest.mark.unit
def test_normalize_email_lowercases_and_validates() -> None:
    assert normalize_email("  Jamie@Example.COM ") == "jamie@example.com"
    assert normalize_email("not-an-email") is None


@pytest.mark.unit
def test_correlation_row_from_email_uses_email_as_identity_key() -> None:
    row = correlation_row_from_email(
        app="salesforce",
        app_identity_external_id="005abc",
        email="Jamie@Example.com",
        display_name="Jamie Example",
    )

    assert row is not None
    assert row["identity_external_id"] == "jamie@example.com"


@pytest.mark.unit
def test_email_from_user_prefers_email_then_username() -> None:
    assert email_from_user({"Email": "jamie@example.com", "Username": "jexample"}) == "jamie@example.com"
    assert email_from_user({"Email": None, "Username": "jamie@example.com"}) == "jamie@example.com"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_correlate_app_identities_by_email_merges_has_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_query = AsyncMock()
    monkeypatch.setattr("integrations.identity_correlation.adb.cypher_query", mock_query)

    row = correlation_row_from_email(
        app="salesforce",
        app_identity_external_id="005abc",
        email="jamie@example.com",
        display_name="Jamie",
    )
    assert row is not None

    await correlate_app_identities_by_email([row])

    mock_query.assert_awaited_once()
    assert "HAS_PROFILE" in mock_query.await_args.args[0]
