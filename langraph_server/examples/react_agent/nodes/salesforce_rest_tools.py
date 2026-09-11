"""Salesforce REST tools: inspect (read) and mutate (write)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, model_validator
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError
from sqlalchemy import select

from aegra_api.core.orm import get_metadata_session_maker
from common.models import AppIntegration
from examples.react_agent.context import Context
from examples.react_agent.salesforce_client import make_salesforce_client

logger = logging.getLogger(__name__)

_ALLOWED_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_SERVICES_PREFIX_RE = re.compile(r"^/?services/data/v[\d.]+/?", re.IGNORECASE)
_MUTATE_METHODS: dict[str, str] = {
    "create": "POST",
    "update": "PATCH",
    "upsert": "PUT",
    "delete": "DELETE",
}


class SalesforceInspectInput(BaseModel):
    """Read-only inspection of Salesforce org state."""

    soql: str | None = Field(
        default=None,
        description="SOQL SELECT to run, for example 'SELECT Id, Name FROM PermissionSet LIMIT 20'.",
    )
    path: str | None = Field(
        default=None,
        description=(
            "REST path to retrieve or describe, relative to /services/data/vXX.X/, "
            "for example 'sobjects/PermissionSet/describe' or 'sobjects/User/005...'."
        ),
    )
    query_params: dict[str, str] | None = Field(
        default=None,
        description="Optional query-string parameters when using path.",
    )

    @model_validator(mode="after")
    def require_soql_or_path(self) -> SalesforceInspectInput:
        soql = (self.soql or "").strip()
        path = (self.path or "").strip()
        if bool(soql) == bool(path):
            msg = "Provide exactly one of soql or path"
            raise ValueError(msg)
        return self


class SalesforceMutateInput(BaseModel):
    """Create, update, or delete Salesforce records."""

    operation: Literal["create", "update", "upsert", "delete"] = Field(
        description="create a record, update fields, upsert, or delete.",
    )
    path: str = Field(
        description=(
            "REST path relative to /services/data/vXX.X/, for example "
            "'sobjects/PermissionSetAssignment' or 'sobjects/PermissionSetAssignment/{id}'."
        ),
    )
    json_body: dict[str, Any] | None = Field(
        default=None,
        description="JSON body for create, update, or upsert.",
    )
    query_params: dict[str, str] | None = Field(
        default=None,
        description="Optional query-string parameters.",
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


def _inspect_salesforce(
    sf: Salesforce,
    *,
    soql: str | None,
    path: str | None,
    query_params: dict[str, str] | None,
) -> str:
    query = (soql or "").strip()
    if query:
        return _run_salesforce_rest(sf, method="GET", path="query", query_params={"q": query})
    return _run_salesforce_rest(
        sf,
        method="GET",
        path=path or "",
        query_params=query_params,
    )


def _mutate_salesforce(
    sf: Salesforce,
    *,
    operation: str,
    path: str,
    json_body: dict[str, Any] | None,
    query_params: dict[str, str] | None,
) -> str:
    method = _MUTATE_METHODS[operation]
    return _run_salesforce_rest(
        sf,
        method=method,
        path=path,
        query_params=query_params,
        json_body=json_body,
    )


async def _salesforce_client(runtime: Runtime[Context]) -> Salesforce:
    integration_username = await resolve_salesforce_integration_username(tenant_id=runtime.context.tenant_id)
    return make_salesforce_client(username=integration_username)


async def build_salesforce_rest_tools(
    runtime: Runtime[Context],
    *,
    include_read: bool = True,
    include_write: bool = True,
) -> list[StructuredTool]:
    """Build Salesforce inspect and/or mutate tools for the connected org."""
    sf = await _salesforce_client(runtime)
    tools: list[StructuredTool] = []

    if include_read:

        def salesforce_inspect(
            soql: str | None = None,
            path: str | None = None,
            query_params: dict[str, str] | None = None,
        ) -> str:
            return _inspect_salesforce(sf, soql=soql, path=path, query_params=query_params)

        tools.append(
            StructuredTool.from_function(
                func=salesforce_inspect,
                name="salesforce_inspect",
                description=(
                    "Inspect Salesforce org state without changing it. "
                    "Run SOQL or GET a resource (describe, retrieve, list). "
                    "Cannot create, update, or delete records."
                ),
                args_schema=SalesforceInspectInput,
            )
        )

    if include_write:

        def salesforce_mutate(
            operation: Literal["create", "update", "upsert", "delete"],
            path: str,
            json_body: dict[str, Any] | None = None,
            query_params: dict[str, str] | None = None,
        ) -> str:
            return _mutate_salesforce(
                sf,
                operation=operation,
                path=path,
                json_body=json_body,
                query_params=query_params,
            )

        tools.append(
            StructuredTool.from_function(
                func=salesforce_mutate,
                name="salesforce_mutate",
                description=(
                    "Change Salesforce org data: create, update, upsert, or delete records "
                    "(for example assign a permission set). Use salesforce_inspect to look up IDs first."
                ),
                args_schema=SalesforceMutateInput,
            )
        )

    logger.info(
        "salesforce_rest_tools: tenant_id=%s include_read=%s include_write=%s tool_count=%d",
        runtime.context.tenant_id.strip(),
        include_read,
        include_write,
        len(tools),
    )
    return tools
