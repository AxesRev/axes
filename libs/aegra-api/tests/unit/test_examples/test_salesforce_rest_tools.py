"""Tests for Salesforce REST grant-execution tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from examples.react_agent.context import Context
from examples.react_agent.nodes.salesforce_rest_tools import (
    _normalize_rest_path,
    _run_salesforce_rest,
    build_salesforce_rest_tools,
    resolve_salesforce_integration_username,
)
from simple_salesforce.exceptions import SalesforceGeneralError


def test_normalize_rest_path_strips_services_prefix() -> None:
    assert _normalize_rest_path("/services/data/v67.0/query?q=SELECT+Id+FROM+User") == "query?q=SELECT+Id+FROM+User"
    assert _normalize_rest_path("sobjects/Account/describe") == "sobjects/Account/describe"


def test_run_salesforce_rest_formats_success_json() -> None:
    sf = MagicMock()
    sf.restful.return_value = {"totalSize": 1, "records": [{"Id": "005"}]}

    output = _run_salesforce_rest(
        sf,
        method="GET",
        path="query?q=SELECT+Id+FROM+User+LIMIT+1",
    )

    assert output.startswith("HTTP 200")
    assert '"totalSize": 1' in output
    sf.restful.assert_called_once_with(
        "query?q=SELECT+Id+FROM+User+LIMIT+1",
        method="GET",
        params=None,
        json=None,
    )


def test_run_salesforce_rest_formats_salesforce_error() -> None:
    sf = MagicMock()
    sf.restful.side_effect = SalesforceGeneralError(
        "https://example.my.salesforce.com/services/data/v67.0/sobjects/Bad",
        400,
        "sobjects/Bad",
        b"Malformed request",
    )

    output = _run_salesforce_rest(sf, method="POST", path="sobjects/Bad", json_body={"Name": "x"})

    assert output.startswith("HTTP 400")
    assert "Malformed request" in output


@pytest.mark.asyncio
async def test_resolve_salesforce_integration_username_reads_tenant_config() -> None:
    integration = MagicMock()
    integration.config = {"integration_username": "axes.integration@example.com"}

    session = AsyncMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None

    with (
        patch(
            "examples.react_agent.nodes.salesforce_rest_tools.get_metadata_session_maker",
            return_value=lambda: session_context,
        ),
        patch(
            "examples.react_agent.nodes.salesforce_rest_tools.find_salesforce_app_integration_for_tenant",
            new=AsyncMock(return_value=integration),
        ) as mock_find,
    ):
        username = await resolve_salesforce_integration_username(tenant_id="tenant-1")

    assert username == "axes.integration@example.com"
    mock_find.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_salesforce_rest_tools_returns_one_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MagicMock()
    runtime.context = Context(tenant_id="tenant-1")

    async def fake_resolve(*, tenant_id: str) -> str:
        assert tenant_id == "tenant-1"
        return "axes.integration@example.com"

    fake_sf = MagicMock()
    monkeypatch.setattr(
        "examples.react_agent.nodes.salesforce_rest_tools.resolve_salesforce_integration_username",
        fake_resolve,
    )
    monkeypatch.setattr(
        "examples.react_agent.nodes.salesforce_rest_tools.make_salesforce_client",
        lambda *, username: fake_sf,
    )

    tools = await build_salesforce_rest_tools(runtime)

    assert len(tools) == 1
    assert tools[0].name == "salesforce_rest"

    output = tools[0].invoke(
        {
            "method": "GET",
            "path": "query?q=SELECT+Id+FROM+User+LIMIT+1",
        }
    )
    assert output.startswith("HTTP 200")
