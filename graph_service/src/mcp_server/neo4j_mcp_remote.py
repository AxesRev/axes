"""Run Neo4j ``mcp-neo4j-cypher`` over HTTP for LangChain remote MCP clients.

This process stays up while Docker (or your supervisor) runs it; the agent uses
``MultiServerMCPClient`` with ``transport: \"http\"`` instead of spawning ``uvx``.

Configuration uses the same environment variables as upstream ``mcp-neo4j-cypher``
(see PyPI / Neo4j docs). This entrypoint forces ``NEO4J_TRANSPORT=http`` and sets
defaults for a network-facing MCP listener.

Bolt credentials stay in this service only; the LangGraph agent uses ``NEO4J_MCP_HOST``
(HTTP base, ``/mcp`` appended in tools), not the database password.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from mcp_neo4j_cypher import server as neo4j_mcp_server
from mcp_neo4j_cypher.utils import process_config


def _force_http_listener_defaults() -> None:
    """Apply defaults suitable for a long-lived remote MCP server."""
    os.environ["NEO4J_TRANSPORT"] = "http"
    os.environ.setdefault("NEO4J_MCP_SERVER_HOST", "0.0.0.0")
    os.environ.setdefault("NEO4J_MCP_SERVER_PORT", "8811")
    os.environ.setdefault("NEO4J_MCP_SERVER_PATH", "/mcp/")
    os.environ.setdefault("NEO4J_READ_ONLY", "true")
    os.environ.setdefault("NEO4J_SCHEMA_SAMPLE_SIZE", "1000")
    # Align with graph_service GitHub fetcher env (`NEO4J_USER`).
    if os.getenv("NEO4J_USERNAME") is None and os.getenv("NEO4J_USER"):
        os.environ["NEO4J_USERNAME"] = os.environ["NEO4J_USER"]


def main() -> None:
    """Parse CLI (optional overrides), merge env via ``process_config``, run HTTP MCP."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    _force_http_listener_defaults()

    parser = argparse.ArgumentParser(
        description="Neo4j MCP remote server (HTTP); powered by mcp-neo4j-cypher",
    )
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--namespace", default=None)
    parser.add_argument("--server-path", default=None)
    parser.add_argument("--server-host", default=None)
    parser.add_argument("--server-port", default=None, type=int)
    parser.add_argument("--allow-origins", default=None)
    parser.add_argument("--allowed-hosts", default=None)
    parser.add_argument("--read-timeout", type=int, default=None)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--token-limit", default=None)
    parser.add_argument("--schema-sample-size", type=int, default=None)

    args = parser.parse_args()
    config = process_config(args)
    asyncio.run(neo4j_mcp_server.main(**config))


if __name__ == "__main__":
    main()
