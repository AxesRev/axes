"""Run Neo4j ``mcp-neo4j-cypher`` over HTTP for LangChain remote MCP clients.

``Neo4jMcpSettings`` reads env (and ``.env``).
Those values are passed into ``mcp-neo4j-cypher`` as Python kwargs.
"""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv
from mcp_neo4j_cypher import server as neo4j_mcp_server
from mcp_neo4j_cypher.server import create_mcp_server as _create_mcp_server
from starlette.responses import JSONResponse

from neo4j_mcp.settings import Neo4jMcpSettings


def _create_mcp_server_with_health(*args, **kwargs):
    mcp = _create_mcp_server(*args, **kwargs)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request):
        return JSONResponse({"status": "ok"})

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    load_dotenv(override=False)
    settings = Neo4jMcpSettings()

    neo4j_mcp_server.create_mcp_server = _create_mcp_server_with_health
    asyncio.run(
        neo4j_mcp_server.main(
            db_url=settings.NEO4J_URI,
            username=settings.username,
            password=settings.NEO4J_PASSWORD,
            database=settings.NEO4J_DATABASE,
            transport=settings.NEO4J_TRANSPORT,
            host=settings.NEO4J_MCP_SERVER_HOST,
            port=settings.NEO4J_MCP_SERVER_PORT,
            path=settings.NEO4J_MCP_SERVER_PATH,
            allowed_hosts=settings.allowed_hosts,
            read_only=settings.NEO4J_READ_ONLY,
            schema_sample_size=settings.NEO4J_SCHEMA_SAMPLE_SIZE,
        )
    )


if __name__ == "__main__":
    main()
