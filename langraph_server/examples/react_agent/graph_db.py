"""Per-tenant ArcadeDB access for the agent.

Every call runs as the tenant's read-only ArcadeDB user against the tenant's own
database, so ArcadeDB refuses writes and any other tenant's data whatever the query.

* ``read_graph`` runs the agent's fixed Cypher over Bolt with the official neo4j driver.
* ``graph_tools`` exposes ArcadeDB's built-in MCP ``query`` and ``get_schema`` tools to the
  LLM with the database argument pinned to the tenant's database.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Literal

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter
from langchain_core.tools import BaseTool, StructuredTool
from neo4j import READ_ACCESS, AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable, SessionExpired
from pydantic import BaseModel, Field

from aegra_api.settings import settings
from common.graph_tenancy import tenant_database, tenant_reader_password, tenant_reader_user

logger = logging.getLogger(__name__)

QUERY_TOOL_NAME = "query_graph"
SCHEMA_TOOL_NAME = "get_graph_schema"
_MCP_QUERY_TOOL = "query"
_MCP_SCHEMA_TOOL = "get_schema"

_drivers: dict[str, AsyncDriver] = {}


def _tenant_key() -> str:
    key = settings.app.ARCADEDB_TENANT_KEY.strip()
    if not key:
        raise RuntimeError("ARCADEDB_TENANT_KEY is not configured")
    return key


def _credentials(tenant_id: str) -> tuple[str, str, str]:
    tenant_id = tenant_id.strip()
    if not tenant_id:
        raise RuntimeError("tenant_id is required for graph access")
    return (
        tenant_database(tenant_id),
        tenant_reader_user(tenant_id),
        tenant_reader_password(tenant_id, _tenant_key()),
    )


def _driver(tenant_id: str) -> tuple[AsyncDriver, str]:
    database, user, password = _credentials(tenant_id)
    driver = _drivers.get(database)
    if driver is None:
        driver = AsyncGraphDatabase.driver(settings.app.ARCADEDB_BOLT_URI, auth=(user, password))
        _drivers[database] = driver
    return driver, database


def _is_stale_connection(exc: Exception) -> bool:
    """Ingestion drops and recreates the tenant database and reader user, which kills open connections."""
    if isinstance(exc, (AuthError, ServiceUnavailable, SessionExpired)):
        return True
    if isinstance(exc, Neo4jError):
        code = exc.code or ""
        return code.startswith("Neo.ClientError.Security") or "AUTHENTICATION" in (exc.message or "")
    return False


async def _reset_driver(database: str) -> None:
    driver = _drivers.pop(database, None)
    if driver is not None:
        try:
            await driver.close()
        except Exception as exc:  # noqa: BLE001 - the old driver is already broken
            logger.debug("graph_driver_close_failed database=%s error=%s", database, exc)


async def read_graph(tenant_id: str, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a read-only Cypher query on the tenant's graph and return its rows.

    Reconnects once when the cached connection went stale (for example after the graph was re-ingested).
    """
    for attempt in (1, 2):
        driver, database = _driver(tenant_id)
        try:
            async with driver.session(database=database, default_access_mode=READ_ACCESS) as session:
                result = await session.run(query, params or {})
                return [record.data() async for record in result]
        except Exception as exc:
            if attempt == 2 or not _is_stale_connection(exc):
                raise
            logger.warning("graph_driver_stale database=%s error=%s; reconnecting", database, exc)
            await _reset_driver(database)
    raise AssertionError("unreachable")


def _mcp_client(tenant_id: str) -> Client[Any]:
    _, user, password = _credentials(tenant_id)
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    url = settings.app.ARCADEDB_HTTP_URL.rstrip("/") + "/api/v1/mcp"
    return Client(StreamableHttpTransport(url, headers={"Authorization": f"Basic {token}"}))


def _tool_text(result: Any) -> str:
    content = result[0] if isinstance(result, tuple) else result
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in content
            if not isinstance(block, dict) or block.get("type") == "text"
        )
    return str(content)


class _QueryArgs(BaseModel):
    query: str = Field(description="Read-only query against the access graph. Use Cypher unless SQL is simpler.")
    language: Literal["cypher", "sql"] = Field(default="cypher", description="Query language")
    limit: int = Field(default=200, ge=1, le=1000, description="Maximum rows to return")


async def graph_tools(tenant_id: str) -> list[BaseTool]:
    """LLM tools backed by ArcadeDB's MCP server, pinned to the tenant's database."""
    database, _, _ = _credentials(tenant_id)
    mcp_tools = {tool.name: tool for tool in await MCPAdapter(_mcp_client(tenant_id)).list_tools()}
    query_tool = mcp_tools.get(_MCP_QUERY_TOOL)
    schema_tool = mcp_tools.get(_MCP_SCHEMA_TOOL)
    if query_tool is None or schema_tool is None:
        logger.warning("graph_tools: ArcadeDB MCP tools missing, found=%s", sorted(mcp_tools))
        return []

    async def query_graph(query: str, language: str = "cypher", limit: int = 200) -> str:
        result = await query_tool.ainvoke({"database": database, "language": language, "query": query, "limit": limit})
        return _tool_text(result)

    async def get_graph_schema() -> str:
        return _tool_text(await schema_tool.ainvoke({"database": database}))

    return [
        StructuredTool.from_function(
            coroutine=query_graph,
            name=QUERY_TOOL_NAME,
            description=(
                "Run a read-only Cypher (or SQL) query on this tenant's access graph "
                "(identities, groups, profiles, resources and HAS_PERMISSION grants). Returns JSON records."
            ),
            args_schema=_QueryArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_graph_schema,
            name=SCHEMA_TOOL_NAME,
            description="List the access graph's vertex and edge types with their indexes.",
        ),
    ]
