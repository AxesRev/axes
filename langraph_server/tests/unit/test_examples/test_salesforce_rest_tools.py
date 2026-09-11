"""Tests for the Salesforce REST API tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from simple_salesforce.exceptions import SalesforceGeneralError

from examples.react_agent.context import Context
from examples.react_agent.nodes.salesforce_rest_tools import (
    SalesforceApiCall,
    SalesforceApiReadCall,
    _normalize_rest_path,
    _run_salesforce_rest,
    _salesforce_api_call,
    build_salesforce_rest_tools,
    resolve_salesforce_integration_username,
)


def test_normalize_rest_path_strips_services_prefix() -> None:
    assert _normalize_rest_path("/services/data/v67.0/query?q=SELECT+Id+FROM+User") == "query?q=SELECT+Id+FROM+User"
    assert _normalize_rest_path("sobjects/Account/describe") == "sobjects/Account/describe"


def test_api_call_joins_segments_and_skips_blanks() -> None:
    describe = SalesforceApiCall(
        method="GET",
        root="sobjects",
        sobject="PermissionSet",
        identifier="describe",
    )
    create = SalesforceApiCall(
        method="POST",
        root="sobjects",
        sobject="PermissionSetAssignment",
        body={"AssigneeId": "005", "PermissionSetId": "0PS"},
    )
    row = SalesforceApiCall(
        method="PATCH",
        root="sobjects",
        sobject="User",
        identifier="005gL00000JQRHlQAP",
        body={"UserPermissionsMarketingUser": True},
    )

    assert describe.rest_path() == "sobjects/PermissionSet/describe"
    assert create.rest_path() == "sobjects/PermissionSetAssignment"
    assert row.rest_path() == "sobjects/User/005gL00000JQRHlQAP"


def test_api_call_schema_rejects_slashes_in_segments() -> None:
    with pytest.raises(ValidationError):
        SalesforceApiCall(method="GET", root="sobjects", sobject="objects/PermissionSet")
    with pytest.raises(ValidationError):
        SalesforceApiCall(
            method="GET",
            root="sobjects",
            sobject="PermissionSet",
            identifier="describe/foo",
        )


def test_api_call_query_puts_soql_in_q_param() -> None:
    payload = SalesforceApiCall(method="GET", root="query", q="SELECT Id FROM PermissionSet")
    assert payload.rest_path() == "query"
    assert payload.query_params() == {"q": "SELECT Id FROM PermissionSet"}


def test_read_schema_rejects_non_get() -> None:
    with pytest.raises(ValidationError):
        SalesforceApiReadCall(method="POST", root="sobjects", sobject="Account", body={"Name": "x"})


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


def test_salesforce_api_call_runs_soql_and_describe() -> None:
    sf = MagicMock()
    sf.restful.return_value = {"totalSize": 0, "records": []}
    _salesforce_api_call(
        sf,
        SalesforceApiCall(method="GET", root="query", q="SELECT Id FROM PermissionSet"),
    )
    sf.restful.assert_called_with(
        "query",
        method="GET",
        params={"q": "SELECT Id FROM PermissionSet"},
        json=None,
    )

    sf.restful.return_value = {"name": "PermissionSet"}
    _salesforce_api_call(
        sf,
        SalesforceApiCall(method="GET", root="sobjects", sobject="PermissionSet", identifier="describe"),
    )
    sf.restful.assert_called_with(
        "sobjects/PermissionSet/describe",
        method="GET",
        params=None,
        json=None,
    )


def test_salesforce_api_call_create_posts() -> None:
    sf = MagicMock()
    sf.restful.return_value = {"id": "0Pa", "success": True}
    body = {"AssigneeId": "005", "PermissionSetId": "0PS"}

    _salesforce_api_call(
        sf,
        SalesforceApiCall(
            method="POST",
            root="sobjects",
            sobject="PermissionSetAssignment",
            body=body,
        ),
    )

    sf.restful.assert_called_once_with(
        "sobjects/PermissionSetAssignment",
        method="POST",
        params=None,
        json=body,
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
async def test_build_salesforce_rest_tools_returns_one_api_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MagicMock()
    runtime.context = Context(tenant_id="tenant-1")
    fake_sf = MagicMock()
    fake_sf.restful.return_value = {"totalSize": 0, "records": []}
    _patch_salesforce_client(monkeypatch, fake_sf)

    tools = await build_salesforce_rest_tools(runtime)

    assert [tool.name for tool in tools] == ["salesforce_api"]
    output = tools[0].invoke({"method": "GET", "root": "query", "q": "SELECT Id FROM User LIMIT 1"})
    assert output.startswith("HTTP 200")
    fake_sf.restful.assert_called_with(
        "query",
        method="GET",
        params={"q": "SELECT Id FROM User LIMIT 1"},
        json=None,
    )


@pytest.mark.asyncio
async def test_build_salesforce_rest_tools_read_only_rejects_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MagicMock()
    runtime.context = Context(tenant_id="tenant-1")
    fake_sf = MagicMock()
    _patch_salesforce_client(monkeypatch, fake_sf)

    tools = await build_salesforce_rest_tools(runtime, include_read=True, include_write=False)

    assert [tool.name for tool in tools] == ["salesforce_api"]
    with pytest.raises(ValidationError):
        tools[0].invoke(
            {
                "method": "POST",
                "root": "sobjects",
                "sobject": "Account",
                "body": {"Name": "x"},
            }
        )
    fake_sf.restful.assert_not_called()
