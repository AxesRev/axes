"""Cypher tool — business logic layer.

Tool functions in this module are plain async callables with no MCP
coupling.  They are registered on the FastMCP instance in
``server/app.py``.  This separation keeps the logic independently
testable and free of framework concerns.

TODO: replace the dummy implementation with real Neo4j queries using the
helpers in ``neo4j_mcp.db.queries``.
"""

from typing import Any


async def execute_cypher(
    query: str,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Execute a Cypher query against Neo4j and return the results.

    Args:
        query: A valid Cypher query string.
        parameters: Optional key/value parameters to bind into the query.

    Returns:
        Query results serialised as a JSON string.
    """
    # TODO: wire up to neo4j_mcp.db.queries.run_read_query / run_write_query
    return "hello world"
