"""FastMCP server definition.

This module is the single place where:
  - the FastMCP instance is created
  - tools are declared (logic delegated to ``neo4j_mcp.tools.*``)
  - the ASGI app is exported for uvicorn

The visible ``run_cypher`` description is overwritten at startup once
``CALL db.schema.visualization()`` succeeds (see ``server/lifespan.py``).

Run standalone:
    uvicorn neo4j_mcp.server.app:app --host 0.0.0.0 --port 8001
    # or
    python -m neo4j_mcp
"""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from neo4j_mcp.server.lifespan import neo4j_lifespan
from neo4j_mcp.settings import get_settings
from neo4j_mcp.tools import cypher as _cypher

_settings = get_settings()

mcp: FastMCP = FastMCP(
    name=_settings.mcp_server_name,
    lifespan=neo4j_lifespan,
)


# ---------------------------------------------------------------------------
# Tool registrations — placeholder description replaced after schema snapshot.
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_cypher(
    query: str,
    parameters: dict[str, Any] | None = None,
    *,
    ctx: Context,
) -> str:
    """Placeholder — overridden by lifespan once Neo4j schema visualization loads."""
    return await _cypher.run_cypher(query, parameters, ctx=ctx)


# ASGI app — used by uvicorn and importable for Starlette mounting
app = mcp.streamable_http_app()
