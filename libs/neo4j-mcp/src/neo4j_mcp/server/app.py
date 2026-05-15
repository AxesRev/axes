"""FastMCP server definition.

This module is the single place where:
  - the FastMCP instance is created
  - all tools are declared (logic delegated to ``neo4j_mcp.tools.*``)
  - the ASGI app is exported for uvicorn

Run standalone:
    uvicorn neo4j_mcp.server.app:app --host 0.0.0.0 --port 8001
    # or
    python -m neo4j_mcp
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from neo4j_mcp.server.lifespan import neo4j_lifespan
from neo4j_mcp.settings import get_settings
from neo4j_mcp.tools import cypher as _cypher

_settings = get_settings()

mcp: FastMCP = FastMCP(
    name=_settings.mcp_server_name,
    lifespan=neo4j_lifespan,
)


# ---------------------------------------------------------------------------
# Tool registrations
# Each @mcp.tool() call is a thin adapter: it declares the MCP-visible
# signature and docstring, then delegates to the logic in tools/*.
# ---------------------------------------------------------------------------


@mcp.tool()
async def execute_cypher(
    query: str,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Execute a Cypher query against the Neo4j database.

    Args:
        query: A valid Cypher query string, e.g. ``MATCH (n) RETURN n LIMIT 5``.
        parameters: Optional parameter map bound into the query at execution time.

    Returns:
        Query results as a JSON string.
    """
    return await _cypher.execute_cypher(query, parameters)


# ASGI app — used by uvicorn and importable for Starlette mounting
app = mcp.streamable_http_app()
