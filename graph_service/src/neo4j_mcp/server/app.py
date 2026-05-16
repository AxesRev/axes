"""FastMCP server definition.

This module is the single place where:
  - the FastMCP instance is created
  - tools and resources are declared (logic delegated to ``neo4j_mcp.tools.*``)
  - the ASGI app is exported for uvicorn

The graph schema schematic (``CALL db.schema.visualization()``) is exposed as MCP
resource ``neo4j://schema``. Tool ``run_cypher`` uses structured Pydantic I/O so
MCP ``inputSchema`` / ``outputSchema`` are populated for LangChain MCP adapters.

Run standalone:
    uvicorn neo4j_mcp.server.app:app --host 0.0.0.0 --port 8001
    # or
    python -m neo4j_mcp
"""

from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from neo4j_mcp.schemas import RunCypherOutput
from neo4j_mcp.server.lifespan import AppContext, neo4j_lifespan
from neo4j_mcp.settings import get_settings
from neo4j_mcp.tools import cypher as _cypher

_settings = get_settings()

mcp: FastMCP = FastMCP(
    name=_settings.mcp_server_name,
    lifespan=neo4j_lifespan,
)


@mcp.resource(
    "neo4j://schema",
    name="neo4j_schema",
    title="Neo4j schema schematic",
    description=(
        "Machine-readable JSON from CALL db.schema.visualization(): node patterns, "
        "relationship patterns, indexes, and constraints."
    ),
    mime_type="application/json",
)
async def neo4j_schema_snapshot(ctx: Context) -> str:
    """Return the cached schema schematic JSON from lifespan."""
    app_ctx: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    return app_ctx.schema_json


@mcp.tool(
    structured_output=True,
    description=(
        "Execute read-only Cypher against Neo4j. "
        "Load labels and relationship patterns from MCP resource neo4j://schema first."
    ),
)
async def run_cypher(
    query: Annotated[str, Field(description="Read-only Cypher query.")],
    parameters: Annotated[
        dict[str, Any] | None,
        Field(description="Optional parameters bound as $keys in the query."),
    ] = None,
    *,
    ctx: Context,
) -> RunCypherOutput:
    """Run parameterized read-only Cypher; returns structured rows."""
    return await _cypher.run_cypher(query, parameters, ctx=ctx)


# ASGI app — used by uvicorn and importable for Starlette mounting
app = mcp.streamable_http_app()
