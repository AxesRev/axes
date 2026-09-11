"""Tests for Salesforce REST inspect/mutate tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from simple_salesforce.exceptions import SalesforceGeneralError

from examples.react_agent.context import Context
from examples.react_agent.nodes.salesforce_rest_tools import (
    SalesforceInspectInput,
    _inspect_salesforce,
    _mutate_salesforce,
    _normalize_rest_path,
    _run_salesforce_rest,
    build_salesforce_rest_tools,
    resolve_salesforce_integration_username,
)


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


def test_inspect_salesforce_runs_soql_as_query() -> None:
    sf = MagicMock()
    sf.restful.return_value = {"totalSize": 0, "records": []}

    _inspect_salesforce(sf, soql="SELECT Id FROM PermissionSet", path=None, query_params=None)

    sf.restful.assert_called_once_with(
        "query",
        method="GET",
        params={"q": "SELECT Id FROM PermissionSet"},
        json=None,
    )


def test_inspect_salesforce_gets_describe_path() -> None:
    sf = MagicMock()
    sf.restful.return_value = {"name": "PermissionSet"}

    _inspect_salesforce(sf, soql=None, path="sobjects/PermissionSet/describe", query_params=None)

    sf.restful.assert_called_once_with(
        "sobjects/PermissionSet/describe",
        method="GET",
        params=None,
        json=None,
    )


def test_inspect_input_requires_exactly_one_of_soql_or_path() -> None:
    with pytest.raises(ValidationError):
        SalesforceInspectInput()
    with pytest.raises(ValidationError):
        SalesforceInspectInput(soql="SELECT Id FROM User", path="sobjects/User/describe")


def test_mutate_salesforce_create_posts() -> None:
    sf = MagicMock()
    sf.restful.return_value = {"id": "0Pa", "success": True}

    _mutate_salesforce(
        sf,
        operation="create",
        path="sobjects/PermissionSetAssignment",
        json_body={"AssigneeId": "005", "PermissionSetId": "0PS"},
        query_params=None,
    )

    sf.restful.assert_called_once_with(
        "sobjects/PermissionSetAssignment",
        method="POST",
        params=None,
        json={"AssigneeId": "005", "PermissionSetId": "0PS"},
    )


def test_run_salesforce_rest_replaces_oversized_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("examples.react_agent.nodes.tools._MAX_TOOL_RESULT_TOKENS", 20)
    sf = MagicMock()
    sf.restful.return_value = {"fields": ["name"] * 400}

    output = _run_salesforce_rest(sf, method="GET", path="sobjects/Account/describe")

    assert "too large" in output
    assert "narrow" in output
    assert '"fields"' not in output


@pytest.mark.asyncio
async def test_resolve_salesforce_integration_username_reads_tenant_config() -> None:
    integration = MagicMock()
    integration.config = {"integration_username": "axes.integration@example.com"}

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = integration
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None

    with patch(
        "examples.react_agent.nodes.salesforce_rest_tools.get_metadata_session_maker",
        return_value=lambda: session_context,
    ):
        username = await resolve_salesforce_integration_username(tenant_id="tenant-1")

    assert username == "axes.integration@example.com"
    session.execute.assert_awaited_once()


def _patch_salesforce_client(monkeypatch: pytest.MonkeyPatch, fake_sf: MagicMock) -> None:
    async def fake_resolve(*, tenant_id: str) -> str:
        assert tenant_id == "tenant-1"
        return "axes.integration@example.com"

    monkeypatch.setattr(
        "examples.react_agent.nodes.salesforce_rest_tools.resolve_salesforce_integration_username",
        fake_resolve,
    )
    monkeypatch.setattr(
        "examples.react_agent.nodes.salesforce_rest_tools.make_salesforce_client",
        lambda *, username: fake_sf,
    )


@pytest.mark.asyncio
async def test_build_salesforce_rest_tools_returns_inspect_and_mutate(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MagicMock()
    runtime.context = Context(tenant_id="tenant-1")
    fake_sf = MagicMock()
    fake_sf.restful.return_value = {"totalSize": 0, "records": []}
    _patch_salesforce_client(monkeypatch, fake_sf)

    tools = await build_salesforce_rest_tools(runtime)

    assert [tool.name for tool in tools] == ["salesforce_inspect", "salesforce_mutate"]
    output = tools[0].invoke({"soql": "SELECT Id FROM User LIMIT 1"})
    assert output.startswith("HTTP 200")
    fake_sf.restful.assert_called_with(
        "query",
        method="GET",
        params={"q": "SELECT Id FROM User LIMIT 1"},
        json=None,
    )


@pytest.mark.asyncio
async def test_build_salesforce_rest_tools_can_omit_mutate(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MagicMock()
    runtime.context = Context(tenant_id="tenant-1")
    _patch_salesforce_client(monkeypatch, MagicMock())

    tools = await build_salesforce_rest_tools(runtime, include_read=True, include_write=False)

    assert [tool.name for tool in tools] == ["salesforce_inspect"]
