"""Salesforce REST grant-execution tool (JWT auth, generic REST client)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

from aegra_api.core.orm import get_metadata_session_maker
from app_integrations.salesforce.client import make_salesforce_client
from app_integrations.salesforce.service import find_salesforce_app_integration_for_tenant
from examples.react_agent.context import Context

logger = logging.getLogger(__name__)

_ALLOWED_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_SERVICES_PREFIX_RE = re.compile(r"^/?services/data/v[\d.]+/?", re.IGNORECASE)


class SalesforceRestInput(BaseModel):
    """Input for a Salesforce REST API call."""

    method: str = Field(description="HTTP method: GET, POST, PATCH, PUT, or DELETE.")
    path: str = Field(
        description=(
            "REST path relative to /services/data/vXX.X/, for example "
            "'query?q=SELECT+Id+FROM+User+LIMIT+1' or 'sobjects/PermissionSetAssignment'."
        ),
    )
    query_params: dict[str, str] | None = Field(
        default=None,
        description="Optional query-string parameters.",
    )
    json_body: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON request body for POST, PATCH, or PUT.",
    )


def _normalize_rest_path(path: str) -> str:
    normalized = path.strip().lstrip("/")
    return _SERVICES_PREFIX_RE.sub("", normalized)


def _format_tool_output(*, status_code: int, body: str) -> str:
    normalized = body.strip()
    if normalized:
        return f"HTTP {status_code}\n\n{normalized}"
    return f"HTTP {status_code}\n\n(empty body)"


def _format_success_payload(payload: Any) -> str:
    if payload is None:
        return _format_tool_output(status_code=204, body="")
    if isinstance(payload, (dict, list)):
        return _format_tool_output(
            status_code=200,
            body=json.dumps(payload, ensure_ascii=False, indent=2),
        )
    return _format_tool_output(status_code=200, body=str(payload))


async def resolve_salesforce_integration_username(*, tenant_id: str) -> str:
    """Load the tenant's Salesforce integration username from app_integrations."""
    normalized_tenant_id = tenant_id.strip()
    if not normalized_tenant_id:
        msg = "tenant_id is required for Salesforce grant tools"
        raise ValueError(msg)

    async with get_metadata_session_maker()() as session:
        integration = await find_salesforce_app_integration_for_tenant(
            tenant_id=normalized_tenant_id,
            session=session,
        )

    if integration is None:
        msg = f"No Salesforce integration configured for tenant {normalized_tenant_id}"
        raise ValueError(msg)

    raw_username = integration.config.get("integration_username")
    if not isinstance(raw_username, str) or not raw_username.strip():
        msg = f"Salesforce integration_username missing for tenant {normalized_tenant_id}"
        raise ValueError(msg)

    return raw_username.strip()


def _run_salesforce_rest(
    sf: Salesforce,
    *,
    method: str,
    path: str,
    query_params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> str:
    normalized_method = method.strip().upper()
    if normalized_method not in _ALLOWED_METHODS:
        msg = f"Unsupported HTTP method: {method}"
        raise ValueError(msg)

    normalized_path = _normalize_rest_path(path)
    if not normalized_path:
        msg = "REST path is required"
        raise ValueError(msg)

    try:
        result = sf.restful(
            normalized_path,
            method=normalized_method,
            params=query_params,
            json=json_body,
        )
    except SalesforceError as err:
        raw_status = getattr(err, "status", 400)
        try:
            status_code = int(raw_status)
        except (TypeError, ValueError):
            status_code = 400
        content = getattr(err, "content", str(err))
        if isinstance(content, bytes):
            body = content.decode("utf-8", errors="replace")
        else:
            body = str(content)
        return _format_tool_output(status_code=status_code, body=body)

    return _format_success_payload(result)


async def build_salesforce_rest_tools(runtime: Runtime[Context]) -> list[StructuredTool]:
    """Build the Salesforce REST tool for grant execution."""
    integration_username = await resolve_salesforce_integration_username(tenant_id=runtime.context.tenant_id)
    sf = make_salesforce_client(username=integration_username)

    def salesforce_rest(
        method: str,
        path: str,
        query_params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> str:
        return _run_salesforce_rest(
            sf,
            method=method,
            path=path,
            query_params=query_params,
            json_body=json_body,
        )

    tool = StructuredTool.from_function(
        func=salesforce_rest,
        name="salesforce_rest",
        description=(
            "Call the Salesforce REST API for the connected org. "
            "Authentication is handled automatically. "
            "Provide method, path, and optional query_params or json_body."
        ),
        args_schema=SalesforceRestInput,
    )
    logger.info(
        "salesforce_rest_tool: initialized for tenant_id=%s",
        runtime.context.tenant_id.strip(),
    )
    return [tool]
