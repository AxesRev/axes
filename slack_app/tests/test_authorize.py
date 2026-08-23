"""Unit tests for Bolt authorize and Slack install lookup."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_bolt.authorization import AuthorizeResult

from slack_app.bolt import authorize
from slack_app.store import find_slack_bot_token, slack_bot_token


@pytest.mark.unit
def test_slack_bot_token_reads_config() -> None:
    assert slack_bot_token({"bot_token": " xoxb-1 "}) == "xoxb-1"
    assert slack_bot_token({}) == ""
    assert slack_bot_token(None) == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_slack_bot_token_returns_stored_token() -> None:
    integration = MagicMock()
    integration.config = {"team_id": "T123", "bot_token": "xoxb-stored"}
    result = MagicMock()
    result.scalar_one_or_none.return_value = integration
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    token = await find_slack_bot_token(session, team_id="T123")

    assert token == "xoxb-stored"
    session.execute.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_slack_bot_token_returns_empty_when_missing() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    assert await find_slack_bot_token(session, team_id="Tmissing") == ""


@asynccontextmanager
async def _fake_session_scope():
    yield object()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authorize_returns_result_for_installed_workspace() -> None:
    with (
        patch("slack_app.bolt.session_scope", _fake_session_scope),
        patch("slack_app.bolt.find_slack_bot_token", AsyncMock(return_value="xoxb-1")),
    ):
        result = await authorize(None, "T123", None, object(), logging.getLogger("test"))

    assert isinstance(result, AuthorizeResult)
    assert result.team_id == "T123"
    assert result.bot_token == "xoxb-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authorize_returns_none_without_team_id() -> None:
    result = await authorize(None, None, None, object(), logging.getLogger("test"))
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authorize_returns_none_without_install() -> None:
    with (
        patch("slack_app.bolt.session_scope", _fake_session_scope),
        patch("slack_app.bolt.find_slack_bot_token", AsyncMock(return_value="")),
    ):
        result = await authorize(None, "T123", None, object(), logging.getLogger("test"))
    assert result is None
