"""Cypher execution for the Neo4j MCP tool."""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.fastmcp import Context

from neo4j_mcp.server.lifespan import AppContext
from neo4j_mcp.settings import get_settings

_WRITE_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP)\b|\bDETACH\s+DELETE\b",
    re.IGNORECASE | re.DOTALL,
)


def _coerce_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            return str(value)
    return value


def _record_as_json_obj(record: Any) -> dict[str, Any]:
    return {key: _coerce_value(record[key]) for key in record}


async def run_cypher(
    query: str,
    parameters: dict[str, Any] | None = None,
    *,
    ctx: Context,
) -> str:
    """Execute ``query`` with optional ``parameters``; return JSON rows."""
    settings = get_settings()
    if not settings.allow_write_queries and _WRITE_PATTERN.search(query):
        raise ValueError(
            "Write/mutating Cypher is disabled (allow_write_queries=false). "
            "Use read-only queries or enable allow_write_queries in configuration."
        )

    req = ctx.request_context
    app_ctx: AppContext = req.lifespan_context  # type: ignore[assignment]
    driver = app_ctx.driver
    params = parameters if parameters is not None else {}

    records, _summary, _keys = await driver.execute_query(
        query,
        params,
        database_=settings.neo4j_database,
    )
    rows = [_record_as_json_obj(r) for r in records]
    payload = {"rows": rows, "row_count": len(rows)}
    return json.dumps(payload, indent=2)
