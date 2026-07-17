"""Run Neo4j ``mcp-neo4j-cypher`` over HTTP for LangChain remote MCP clients.

Loads a ``.env`` file from the current working directory or a parent (``python-dotenv`` lookup),
then reads configuration only from environment variables understood by ``mcp-neo4j-cypher``.

This entry forces ``NEO4J_TRANSPORT=http`` and sets defaults for a network-facing MCP listener unless
already set in the environment.

The LangGraph agent uses ``NEO4J_MCP_HOST`` only (HTTP base); Bolt credentials stay on this process.
"""

from __future__ import annotations

import asyncio
import logging
import os
from argparse import Namespace

from dotenv import load_dotenv
from mcp_neo4j_cypher import server as neo4j_mcp_server
from mcp_neo4j_cypher.utils import process_config

# ``process_config`` expects an argparse-like namespace; configuration comes from env only.
_PROCESS_CONFIG_ARGS = Namespace(
    db_url=None,
    username=None,
    password=None,
    database=None,
    transport=None,
    namespace=None,
    server_host=None,
    server_port=None,
    server_path=None,
    allow_origins=None,
    allowed_hosts=None,
    read_timeout=None,
    read_only=False,
    token_limit=None,
    schema_sample_size=None,
)


def _force_http_listener_defaults() -> None:
    """Apply defaults suitable for a long-lived remote MCP server."""
    os.environ["NEO4J_TRANSPORT"] = "http"
    os.environ.setdefault("NEO4J_MCP_SERVER_HOST", "0.0.0.0")
    os.environ.setdefault("NEO4J_MCP_SERVER_PORT", "8811")
    os.environ.setdefault("NEO4J_MCP_SERVER_PATH", "/mcp/")
    os.environ.setdefault("NEO4J_READ_ONLY", "true")
    os.environ.setdefault("NEO4J_SCHEMA_SAMPLE_SIZE", "1000")
    if os.getenv("NEO4J_USERNAME") is None and os.getenv("NEO4J_USER"):
        os.environ["NEO4J_USERNAME"] = os.environ["NEO4J_USER"]


def main() -> None:
    """Load ``.env`` from cwd (or parents), apply HTTP defaults, run MCP from environment only."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    load_dotenv(override=False)
    _force_http_listener_defaults()

    config = process_config(_PROCESS_CONFIG_ARGS)
    asyncio.run(neo4j_mcp_server.main(**config))


if __name__ == "__main__":
    main()
