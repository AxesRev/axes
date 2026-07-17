"""Unit tests for Slack Web API client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_app.client import fetch_user_email


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_user_email_returns_profile_email() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "user": {"profile": {"email": "alice@example.com"}},
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("slack_app.client.slack_settings.SLACK_BOT_TOKEN", "xoxb-test"),
        patch("slack_app.client.httpx.AsyncClient", return_value=mock_client),
    ):
        email = await fetch_user_email("U123")

    assert email == "alice@example.com"
    mock_client.get.assert_awaited_once()
    call_kwargs = mock_client.get.await_args.kwargs
    assert call_kwargs["params"] == {"user": "U123"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_user_email_returns_none_when_api_fails() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "missing_scope"}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("slack_app.client.slack_settings.SLACK_BOT_TOKEN", "xoxb-test"),
        patch("slack_app.client.httpx.AsyncClient", return_value=mock_client),
    ):
        email = await fetch_user_email("U123")

    assert email is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_user_email_returns_none_without_token() -> None:
    with patch("slack_app.client.slack_settings.SLACK_BOT_TOKEN", ""):
        email = await fetch_user_email("U123")

    assert email is None
