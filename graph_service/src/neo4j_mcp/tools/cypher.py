"""Cypher execution for the Neo4j MCP tool (read-only)."""

from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import Context

from neo4j_mcp.schemas import RunCypherOutput
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
) -> RunCypherOutput:
    """Execute read-only ``query`` with optional ``parameters``."""
    if _WRITE_PATTERN.search(query):
        raise ValueError(
            "Only read-only Cypher is allowed. Remove CREATE, MERGE, DELETE, SET, REMOVE, DROP, DETACH DELETE."
        )

    settings = get_settings()
    app_ctx: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    driver = app_ctx.driver
    params = parameters if parameters is not None else {}

    records, _summary, _keys = await driver.execute_query(
        query,
        params,
        database_=settings.neo4j_database,
    )
    rows = [_record_as_json_obj(r) for r in records]
    return RunCypherOutput(rows=rows, row_count=len(rows))
