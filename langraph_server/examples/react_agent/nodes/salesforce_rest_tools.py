"""Salesforce REST tool: join Pydantic fields into /services/data/vXX.X/{root}/..."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError
from sqlalchemy import select

from aegra_api.core.orm import get_metadata_session_maker
from common.models import AppIntegration
from examples.react_agent.context import Context
from examples.react_agent.nodes.tools import truncate_tool_text
from examples.react_agent.salesforce_client import make_salesforce_client

logger = logging.getLogger(__name__)

_ALLOWED_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_SERVICES_PREFIX_RE = re.compile(r"^/?services/data/v[\d.]+/?", re.IGNORECASE)
_SEGMENT_PATTERN = r"^[^/?#\s]+$"
_SOBJECT_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"

SalesforceHttpMethod = Literal["GET", "POST", "PATCH", "PUT", "DELETE"]
SalesforceRoot = Literal["sobjects", "query", "queryAll", "search", "limits"]


class SalesforceApiCall(BaseModel):
    """One REST call. Path is root/sobject/identifier/extra, skipping blanks."""

    method: SalesforceHttpMethod = Field(description="HTTP method.")
    root: SalesforceRoot = Field(
        description="First path segment under /services/data/vXX.X/.",
    )
    sobject: str | None = Field(
        default=None,
        pattern=_SOBJECT_PATTERN,
        description="sObject API name, for example PermissionSet or PermissionSetAssignment.",
    )
    identifier: str | None = Field(
        default=None,
        pattern=_SEGMENT_PATTERN,
        description="Next segment: describe, updated, deleted, a record id, or an external-id field name.",
    )
    extra: str | None = Field(
        default=None,
        pattern=_SEGMENT_PATTERN,
        description="Final segment when needed: blob field name or external-id value.",
    )
    q: str | None = Field(
        default=None,
        description="SOQL for query/queryAll, or SOSL for search.",
    )
    body: dict[str, Any] | None = Field(
        default=None,
        description="JSON body for POST, PATCH, or PUT.",
    )
    params: dict[str, str] | None = Field(
        default=None,
        description="Extra query-string parameters, for example start/end on updated.",
    )

    def rest_path(self) -> str:
        return "/".join(part for part in (self.root, self.sobject, self.identifier, self.extra) if part)

    def query_params(self) -> dict[str, str] | None:
        params = dict(self.params or {})
        if self.q:
            params["q"] = self.q
        return params or None


class SalesforceApiReadCall(SalesforceApiCall):
    """Same call shape, GET only."""

    method: Literal["GET"] = "GET"


def _normalize_rest_path(path: str) -> str:
    normalized = path.strip().lstrip("/")
    return _SERVICES_PREFIX_RE.sub("", normalized)


def _format_tool_output(*, status_code: int, body: str) -> str:
    normalized = body.strip()
    if normalized:
        text = f"HTTP {status_code}\n\n{normalized}"
    else:
        text = f"HTTP {status_code}\n\n(empty body)"
    return truncate_tool_text(text)


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
    """Load the tenant's Salesforce integration username from Postgres."""
    normalized_tenant_id = tenant_id.strip()
    if not normalized_tenant_id:
        msg = "tenant_id is required for Salesforce grant tools"
        raise ValueError(msg)

    async with get_metadata_session_maker()() as session:
        result = await session.execute(
            select(AppIntegration).where(
                AppIntegration.tenant_id == normalized_tenant_id,
                AppIntegration.app_name == "salesforce",
            )
        )
        integration = result.scalar_one_or_none()

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


def _salesforce_api_call(sf: Salesforce, payload: SalesforceApiCall) -> str:
    return _run_salesforce_rest(
        sf,
        method=payload.method,
        path=payload.rest_path(),
        query_params=payload.query_params(),
        json_body=payload.body,
    )


async def _salesforce_client(runtime: Runtime[Context]) -> Salesforce:
    integration_username = await resolve_salesforce_integration_username(tenant_id=runtime.context.tenant_id)
    return make_salesforce_client(username=integration_username)


def _args_schema(*, allow_write: bool) -> type[SalesforceApiCall]:
    return SalesforceApiCall if allow_write else SalesforceApiReadCall


async def build_salesforce_rest_tools(
    runtime: Runtime[Context],
    *,
    include_read: bool = True,
    include_write: bool = True,
) -> list[StructuredTool]:
    """Build the Salesforce REST tool for the connected org."""
    if not include_read and not include_write:
        return []

    sf = await _salesforce_client(runtime)
    schema = _args_schema(allow_write=include_write)

    def salesforce_api(**kwargs: Any) -> str:
        return _salesforce_api_call(sf, schema.model_validate(kwargs))

    description = (
        "Call Salesforce REST API. Path is root/sobject/identifier/extra. "
        "GET query with q for SOQL. POST sobjects/{sobject} to create, "
        "PATCH/DELETE sobjects/{sobject}/{id} to update or delete."
    )
    if not include_write:
        description = "Read Salesforce org state. Path is root/sobject/identifier/extra. GET query with q for SOQL."

    logger.info(
        "salesforce_rest_tools: tenant_id=%s include_read=%s include_write=%s tool_count=1",
        runtime.context.tenant_id.strip(),
        include_read,
        include_write,
    )
    return [
        StructuredTool.from_function(
            func=salesforce_api,
            name="salesforce_api",
            description=description,
            args_schema=schema,
        )
    ]
