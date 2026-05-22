"""Tests for GitHub App installation access tokens."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app_integrations.github import installation_token as token_module
from app_integrations.github.installation_token import get_installation_access_token


def test_get_installation_access_token_requires_installation_id() -> None:
    with pytest.raises(ValueError, match="github_installation_id"):
        get_installation_access_token("")


def test_get_installation_access_token_mints_and_caches() -> None:
    token_module._token_cache.clear()

    authorization = MagicMock()
    authorization.token = "ghs_test"
    authorization.expires_at = datetime(2099, 1, 1, tzinfo=UTC)

    integration = MagicMock()
    integration.get_access_token.return_value = authorization

    with patch.object(token_module, "_github_integration", return_value=integration):
        first = get_installation_access_token("42")
        second = get_installation_access_token("42")

    assert first == "ghs_test"
    assert second == "ghs_test"
    integration.get_access_token.assert_called_once_with(42)


def test_get_installation_access_token_requires_app_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    token_module._token_cache.clear()
    monkeypatch.setattr(
        token_module.github_settings,
        "GITHUB_APP_ID",
        0,
    )
    with pytest.raises(ValueError, match="GITHUB_APP_ID"):
        get_installation_access_token("42")
