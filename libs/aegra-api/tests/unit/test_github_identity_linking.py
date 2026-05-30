"""Unit tests for Slack → GitHub OAuth identity linking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app_integrations.github.constants import GITHUB_APP_NAME
from app_integrations.github.extra_app_data import get_github_extra, github_is_linked, set_github_extra
from app_integrations.github.identity_linking import (
    get_github_identity,
    handle_access_request,
    link_github_identity,
)
from app_integrations.github.models import AppIntegration, OAuthState, UserIdentity
from app_integrations.github.oauth_state import create_github_oauth_state, verify_github_oauth_state


@pytest.mark.unit
def test_create_and_verify_github_oauth_state() -> None:
    secret = "test-secret"
    state = create_github_oauth_state("U123", secret, ttl_seconds=300)
    assert verify_github_oauth_state(state, secret) == "U123"


@pytest.mark.unit
def test_github_is_linked_from_extra_app_data() -> None:
    identity = UserIdentity(
        slack_user_id="U1",
        tenant_id="t1",
        extra_app_data={"github": {"user_id": "99", "email": "alice@example.com"}},
    )
    assert github_is_linked(identity)
    assert get_github_extra(identity) == {"user_id": "99", "email": "alice@example.com"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_github_identity_returns_linked_when_extra_app_data_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = UserIdentity(
        id="id-1",
        slack_user_id="U123",
        tenant_id="tenant-1",
        extra_app_data={"github": {"user_id": "42", "email": "octo@users.noreply.github.com"}},
    )
    integration = AppIntegration(
        id="int-1",
        tenant_id="tenant-1",
        app_name=GITHUB_APP_NAME,
        config={"installation_id": "inst-9"},
    )
    session = AsyncMock()
    session.commit = AsyncMock()
    monkeypatch.setattr(
        "app_integrations.github.identity_linking.find_github_app_integration_for_tenant",
        AsyncMock(return_value=integration),
    )

    result = await get_github_identity(identity, session, server_url="http://localhost:8000")

    assert result.status == "LINKED"
    assert result.github_user_id == "42"
    assert result.github_email == "octo@users.noreply.github.com"
    assert result.github_installation_id == "inst-9"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_github_identity_returns_connect_url_when_not_linked() -> None:
    identity = UserIdentity(id="id-1", slack_user_id="U123", tenant_id="tenant-1", extra_app_data={})
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    result = await get_github_identity(identity, session, server_url="http://localhost:8000")

    assert result.status == "NOT_LINKED"
    assert "/auth/github/start?token=" in result.connect_url
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, OAuthState)
    assert added.slack_user_id == "U123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_link_github_identity_stores_extra_app_data_and_deletes_oauth_state() -> None:
    identity = UserIdentity(id="id-1", slack_user_id="U123", tenant_id="tenant-1", extra_app_data={})
    oauth_state = OAuthState(
        token="tok-1",
        slack_user_id="U123",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    session = AsyncMock()
    identity_result = MagicMock()
    identity_result.scalar_one_or_none.return_value = identity
    state_result = MagicMock()
    state_result.scalar_one_or_none.return_value = oauth_state
    session.execute = AsyncMock(side_effect=[identity_result, state_result])
    session.delete = AsyncMock()
    session.commit = AsyncMock()

    updated = await link_github_identity(
        slack_user_id="U123",
        github_user_id="42",
        github_email="octo@example.com",
        oauth_token="tok-1",
        session=session,
    )

    assert updated is identity
    assert get_github_extra(identity) == {"user_id": "42", "email": "octo@example.com"}
    session.delete.assert_awaited_once_with(oauth_state)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_access_request_blocks_when_not_linked() -> None:
    identity = UserIdentity(id="id-1", slack_user_id="U123", tenant_id="tenant-1", extra_app_data={})
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    result = await handle_access_request(
        identity,
        {"text": "hi"},
        session,
        server_url="http://localhost:8000",
    )

    assert result.linked is False
    assert result.not_linked is not None
    assert result.not_linked.status == "NOT_LINKED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_github_extra_merges_other_keys() -> None:
    identity = UserIdentity(
        slack_user_id="U1",
        tenant_id="t1",
        extra_app_data={"salesforce": {"user_id": "sf1"}},
    )
    set_github_extra(identity, user_id="99", email="alice@example.com")
    assert identity.extra_app_data["salesforce"] == {"user_id": "sf1"}
    assert identity.extra_app_data["github"] == {"user_id": "99", "email": "alice@example.com"}
