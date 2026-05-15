"""Unit tests for the execute_cypher tool logic."""

import pytest

from neo4j_mcp.tools.cypher import execute_cypher


@pytest.mark.unit
async def test_execute_cypher_returns_hello_world() -> None:
    result = await execute_cypher("MATCH (n) RETURN n LIMIT 1")
    assert result == "hello world"


@pytest.mark.unit
async def test_execute_cypher_accepts_parameters() -> None:
    result = await execute_cypher("MATCH (n {id: $id}) RETURN n", parameters={"id": "abc"})
    assert result == "hello world"


@pytest.mark.unit
async def test_execute_cypher_parameters_default_to_none() -> None:
    result = await execute_cypher("RETURN 1")
    assert isinstance(result, str)
